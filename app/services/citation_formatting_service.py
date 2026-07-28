"""APA 7 in-text citations and reference-list entries.

Pure and DB-free by design — every rule here is unit-tested in isolation.
A `CitationContext` is built once per export over the *entire* accepted
set, because year-letter disambiguation ("2024a" vs "2024b") is a
property of the whole bibliography, not of any single reference: whether
a citation needs a letter suffix depends on what else is being cited
alongside it.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

#: "Surname, F. M." — the shape Scopus/dataset imports produce.
_SURNAME_FIRST = re.compile(r"^([^,]+),\s*(.+)$")
#: "F. M. Surname" or "Firstname Middle Surname" — Semantic Scholar's shape.
_GIVEN_FIRST_INITIALS = re.compile(r"^((?:[A-Z]\.\s*)+)\s*([A-Za-z\-']+)$")

MAX_ENTRY_AUTHORS = 20
ENTRY_ELLIPSIS_KEEP_FIRST = 19


@dataclass(frozen=True)
class AuthorName:
    family: str
    given_initials: str = ""  # "J. A." or ""

    @property
    def display_family(self) -> str:
        return self.family or "Unknown"


def parse_author_name(raw: str | None) -> AuthorName | None:
    """'Smith, J. A.' | 'Jane A. Smith' | 'J. A. Smith' | 'Smith' -> AuthorName.

    Returns None for blank input so callers can filter it out rather than
    fabricate an author.
    """
    if not raw or not raw.strip():
        return None
    text = raw.strip()

    match = _SURNAME_FIRST.match(text)
    if match:
        family, rest = match.group(1).strip(), match.group(2).strip()
        return AuthorName(family=family, given_initials=_to_initials(rest))

    match = _GIVEN_FIRST_INITIALS.match(text)
    if match:
        initials_part, family = match.group(1).strip(), match.group(2).strip()
        return AuthorName(family=family, given_initials=_to_initials(initials_part))

    parts = text.split()
    if len(parts) == 1:
        return AuthorName(family=parts[0])
    # "Jane A. Smith" / "Jane Smith" — assume the last token is the family
    # name and everything before it is given name(s) to initialize.
    family = parts[-1]
    given = " ".join(parts[:-1])
    return AuthorName(family=family, given_initials=_to_initials(given))


def _to_initials(given: str) -> str:
    """'James Alan' -> 'J. A.'; 'J. A.' -> 'J. A.' (idempotent)."""
    tokens = re.findall(r"[A-Za-z]+", given)
    return " ".join(f"{t[0].upper()}." for t in tokens)


def parse_authors(authors_json: list | None) -> list[AuthorName]:
    """Reads the JSONB shape produced by import/enrichment: a list of
    dicts, usually `{"name": ...}`, tolerating bare strings and blanks.
    """
    if not authors_json:
        return []
    parsed: list[AuthorName] = []
    for entry in authors_json:
        if isinstance(entry, dict):
            raw = entry.get("name")
        elif isinstance(entry, str):
            raw = entry
        else:
            raw = None
        author = parse_author_name(raw)
        if author is not None:
            parsed.append(author)
    return parsed


def _short_title(title: str | None, max_words: int = 4) -> str:
    if not title:
        return "Untitled"
    words = re.findall(r"\S+", title)
    short = " ".join(words[:max_words])
    return f'"{short}"' if len(words) > max_words else f'"{short}"'


def _author_year_key(authors: list[AuthorName], title: str | None) -> str:
    if authors:
        return authors[0].display_family.lower()
    return _short_title(title).lower()


def _in_text_authors(authors: list[AuthorName], title: str | None) -> str:
    if not authors:
        return _short_title(title)
    if len(authors) == 1:
        return authors[0].display_family
    if len(authors) == 2:
        return f"{authors[0].display_family} & {authors[1].display_family}"
    return f"{authors[0].display_family} et al."


def _entry_authors(authors: list[AuthorName]) -> str:
    if not authors:
        return ""
    names = [f"{a.display_family}, {a.given_initials}".rstrip(", ") for a in authors]
    if len(names) == 1:
        joined = names[0]
    elif len(names) == 2:
        joined = f"{names[0]}, & {names[1]}"
    elif len(names) <= MAX_ENTRY_AUTHORS:
        joined = ", ".join(names[:-1]) + f", & {names[-1]}"
    else:
        # APA 7: list the first 19, ellipsis, then the last author.
        kept = names[:ENTRY_ELLIPSIS_KEEP_FIRST]
        joined = ", ".join(kept) + f", . . . {names[-1]}"
    # A name whose initials already end in "." (the common case) must not
    # collect a second, doubled period here.
    return joined if joined.endswith(".") else f"{joined}."


@dataclass(frozen=True)
class Segment:
    """One run of reference-list text; `italic` marks journal/book titles
    so the DOCX writer can preserve APA's italicization without the
    formatting service knowing anything about python-docx.
    """

    text: str
    italic: bool = False


@dataclass(frozen=True)
class FormattedCitation:
    in_text: str  # "(Smith et al., 2023)"
    entry: tuple[Segment, ...]  # full reference-list entry
    sort_key: tuple  # for alphabetising the bibliography


def _year_str(year: int | None) -> str:
    return str(year) if year else "n.d."


def _build_entry(
    authors: list[AuthorName], year: int | None, title: str | None, ref, year_suffix: str
) -> tuple[Segment, ...]:
    segments: list[Segment] = []
    author_text = _entry_authors(authors)
    if author_text:
        segments.append(Segment(f"{author_text} "))
    segments.append(Segment(f"({_year_str(year)}{year_suffix}). "))
    segments.append(Segment(f"{title or 'Untitled'}. "))

    source_title = getattr(ref, "source_title", None)
    if source_title:
        segments.append(Segment(source_title, italic=True))

    doi = getattr(ref, "doi", None)
    link = doi and f"https://doi.org/{doi}" or getattr(ref, "scopus_url", None) or getattr(
        ref, "source_link", None
    )
    if link:
        prefix = ", " if source_title else " "
        segments.append(Segment(f"{prefix}{link}"))
    return tuple(segments)


class CitationContext:
    """Built once per export over the whole accepted set. Owns year-letter
    disambiguation so an in-text citation and its bibliography entry can
    never disagree about which of two same-author, same-year papers is
    "a" and which is "b".
    """

    def __init__(self, references: Sequence, style: str = "APA"):
        if style != "APA":
            raise ValueError(f"Unsupported citation style: {style!r} (only APA is implemented)")

        self._by_id: dict[uuid.UUID, FormattedCitation] = {}
        self._order: list[uuid.UUID] = []

        parsed = [(ref, parse_authors(ref.authors)) for ref in references]

        # Group by (author-or-title key, year) to find which references need
        # a disambiguating letter suffix.
        groups: dict[tuple[str, int | None], list] = {}
        for ref, authors in parsed:
            key = (_author_year_key(authors, ref.title), ref.year)
            groups.setdefault(key, []).append((ref, authors))

        suffix_by_id: dict[uuid.UUID, str] = {}
        for members in groups.values():
            if len(members) < 2:
                continue
            # Stable, deterministic tie-break: sort by title so "a"/"b"
            # assignment doesn't depend on input order.
            members.sort(key=lambda pair: (pair[0].title or "").lower())
            for index, (ref, _authors) in enumerate(members):
                suffix_by_id[ref.id] = chr(ord("a") + index)

        for ref, authors in parsed:
            suffix = suffix_by_id.get(ref.id, "")
            in_text_authors = _in_text_authors(authors, ref.title)
            in_text = f"({in_text_authors}, {_year_str(ref.year)}{suffix})"
            entry = _build_entry(authors, ref.year, ref.title, ref, suffix)
            sort_key = (_author_year_key(authors, ref.title), ref.year or 0, suffix)

            self._by_id[ref.id] = FormattedCitation(in_text=in_text, entry=entry, sort_key=sort_key)
            self._order.append(ref.id)

    def in_text(self, reference_id: uuid.UUID) -> str:
        return self._by_id[reference_id].in_text

    def entry(self, reference_id: uuid.UUID) -> tuple[Segment, ...]:
        return self._by_id[reference_id].entry

    def bibliography(self) -> list[tuple[uuid.UUID, tuple[Segment, ...]]]:
        ordered = sorted(self._order, key=lambda rid: self._by_id[rid].sort_key)
        return [(rid, self._by_id[rid].entry) for rid in ordered]


def build_citation_context(references: Sequence, style: str = "APA") -> CitationContext:
    return CitationContext(references, style=style)


def join_in_text(citations: Sequence[str]) -> str:
    """['(Smith, 2023)', '(Lee et al., 2024)'] -> '(Smith, 2023; Lee et al., 2024)'"""
    if not citations:
        return ""
    if len(citations) == 1:
        return citations[0]
    inner = "; ".join(c.strip("()") for c in citations)
    return f"({inner})"
