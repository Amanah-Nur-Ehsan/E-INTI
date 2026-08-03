import uuid
from dataclasses import dataclass

import pytest

from app.services.citation_formatting_service import (
    build_citation_context,
    join_in_text,
    parse_author_name,
    parse_authors,
)


@dataclass
class FakeRef:
    """Minimal stand-in for ReferencePaper -- only what CitationContext reads."""

    title: str
    year: int | None = None
    authors: list | None = None
    source_title: str | None = None
    doi: str | None = None
    scopus_url: str | None = None
    source_link: str | None = None
    id: uuid.UUID = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.id is None:
            self.id = uuid.uuid4()


# ---------------------------------------------------------------- parsing --


@pytest.mark.parametrize(
    "raw,expected_family,expected_initials",
    [
        ("Smith, J. A.", "Smith", "J. A."),
        ("Smith, James Alan", "Smith", "J. A."),
        ("Jane A. Smith", "Smith", "J. A."),
        ("J. A. Smith", "Smith", "J. A."),
        ("Smith", "Smith", ""),
        ("van der Berg, P.", "van der Berg", "P."),
    ],
)
def test_parse_author_name_shapes(raw, expected_family, expected_initials):
    author = parse_author_name(raw)
    assert author.family == expected_family
    assert author.given_initials == expected_initials


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_parse_author_name_blank_is_none(raw):
    assert parse_author_name(raw) is None


def test_parse_authors_tolerates_mixed_shapes():
    authors = parse_authors([{"name": "Smith, J."}, {"name": "Jane Doe"}, {}, None, "Bare String"])
    families = [a.family for a in authors]
    assert families == ["Smith", "Doe", "String"]


def test_parse_authors_none_or_empty():
    assert parse_authors(None) == []
    assert parse_authors([]) == []


# --------------------------------------------------------- in-text/entry --


def test_single_author():
    ctx = build_citation_context([FakeRef(title="A Paper", year=2023, authors=[{"name": "Smith, J."}])])
    ref_id = next(iter(ctx._by_id))
    assert ctx.in_text(ref_id) == "(Smith, 2023)"


def test_two_authors():
    ctx = build_citation_context(
        [FakeRef(title="A Paper", year=2023, authors=[{"name": "Smith, J."}, {"name": "Lee, B."}])]
    )
    ref_id = next(iter(ctx._by_id))
    assert ctx.in_text(ref_id) == "(Smith & Lee, 2023)"


def test_three_or_more_authors_use_et_al():
    ctx = build_citation_context(
        [
            FakeRef(
                title="A Paper",
                year=2023,
                authors=[{"name": "Smith, J."}, {"name": "Lee, B."}, {"name": "Chen, C."}],
            )
        ]
    )
    ref_id = next(iter(ctx._by_id))
    assert ctx.in_text(ref_id) == "(Smith et al., 2023)"


def test_no_authors_uses_short_title():
    ctx = build_citation_context([FakeRef(title="A Concept-Aligned Explainable AI System", year=2023)])
    ref_id = next(iter(ctx._by_id))
    assert ctx.in_text(ref_id).startswith('("A Concept-Aligned')
    assert "2023" in ctx.in_text(ref_id)


def test_missing_year_is_no_date():
    ctx = build_citation_context([FakeRef(title="A Paper", year=None, authors=[{"name": "Smith, J."}])])
    ref_id = next(iter(ctx._by_id))
    assert ctx.in_text(ref_id) == "(Smith, n.d.)"


def test_duplicate_author_year_gets_disambiguated():
    refs = [
        FakeRef(title="Alpha Study", year=2024, authors=[{"name": "Smith, J."}]),
        FakeRef(title="Beta Study", year=2024, authors=[{"name": "Smith, J."}]),
    ]
    ctx = build_citation_context(refs)
    in_texts = sorted(ctx.in_text(r.id) for r in refs)
    assert in_texts == ["(Smith, 2024a)", "(Smith, 2024b)"]

    # Alphabetical tie-break by title: "Alpha" < "Beta" -> Alpha gets 'a'.
    alpha = next(r for r in refs if r.title == "Alpha Study")
    assert ctx.in_text(alpha.id) == "(Smith, 2024a)"


def test_no_disambiguation_when_only_one_reference_in_the_group():
    refs = [
        FakeRef(title="Solo Study", year=2024, authors=[{"name": "Smith, J."}]),
        FakeRef(title="Other Study", year=2023, authors=[{"name": "Lee, B."}]),
    ]
    ctx = build_citation_context(refs)
    solo = next(r for r in refs if r.title == "Solo Study")
    assert ctx.in_text(solo.id) == "(Smith, 2024)"  # no suffix


def test_entry_authors_two():
    ctx = build_citation_context(
        [
            FakeRef(
                title="A Paper",
                year=2023,
                authors=[{"name": "Smith, J. A."}, {"name": "Lee, B."}],
                source_title="Journal of Testing",
            )
        ]
    )
    ref_id = next(iter(ctx._by_id))
    text = "".join(seg.text for seg in ctx.entry(ref_id))
    assert text.startswith("Smith, J. A., & Lee, B. (2023). A Paper. ")


def test_entry_source_title_is_italic_segment():
    ctx = build_citation_context(
        [
            FakeRef(
                title="A Paper",
                year=2023,
                authors=[{"name": "Smith, J."}],
                source_title="Journal of Testing",
            )
        ]
    )
    ref_id = next(iter(ctx._by_id))
    italics = [seg for seg in ctx.entry(ref_id) if seg.italic]
    assert len(italics) == 1
    assert italics[0].text == "Journal of Testing"


def test_entry_prefers_doi_link():
    ctx = build_citation_context(
        [
            FakeRef(
                title="A Paper",
                year=2023,
                authors=[{"name": "Smith, J."}],
                doi="10.1016/j.example.2023",
                scopus_url="https://scopus.example/should-not-appear",
            )
        ]
    )
    ref_id = next(iter(ctx._by_id))
    text = "".join(seg.text for seg in ctx.entry(ref_id))
    assert "https://doi.org/10.1016/j.example.2023" in text
    assert "scopus.example" not in text


def test_entry_falls_back_to_scopus_url_without_doi():
    ctx = build_citation_context(
        [
            FakeRef(
                title="A Paper",
                year=2023,
                authors=[{"name": "Smith, J."}],
                scopus_url="https://scopus.example/record/1",
            )
        ]
    )
    ref_id = next(iter(ctx._by_id))
    text = "".join(seg.text for seg in ctx.entry(ref_id))
    assert "https://scopus.example/record/1" in text


def test_21_plus_authors_use_ellipsis_rule():
    authors = [{"name": f"Author{i}, X."} for i in range(22)]
    ctx = build_citation_context([FakeRef(title="A Paper", year=2023, authors=authors)])
    ref_id = next(iter(ctx._by_id))
    text = "".join(seg.text for seg in ctx.entry(ref_id))
    assert ". . . " in text
    assert "Author21, X." in text  # last author (0-indexed 21st) still present
    assert text.count("Author") == 20  # 19 kept + the final one, not all 22


def test_bibliography_is_alphabetised():
    refs = [
        FakeRef(title="Zebra Paper", year=2020, authors=[{"name": "Zed, A."}]),
        FakeRef(title="Alpha Paper", year=2020, authors=[{"name": "Aaron, B."}]),
    ]
    ctx = build_citation_context(refs)
    ordered_ids = [rid for rid, _entry in ctx.bibliography()]
    zebra = next(r for r in refs if r.title == "Zebra Paper")
    alpha = next(r for r in refs if r.title == "Alpha Paper")
    assert ordered_ids.index(alpha.id) < ordered_ids.index(zebra.id)


def test_unsupported_style_raises():
    with pytest.raises(ValueError, match="Unsupported citation style"):
        build_citation_context([FakeRef(title="A Paper")], style="MLA")


# ---------------------------------------------------------------- joining --


def test_join_in_text_single():
    assert join_in_text(["(Smith, 2023)"]) == "(Smith, 2023)"


def test_join_in_text_multiple():
    result = join_in_text(["(Smith, 2023)", "(Lee et al., 2024)"])
    assert result == "(Smith, 2023; Lee et al., 2024)"


def test_join_in_text_empty():
    assert join_in_text([]) == ""


# ------------------------------------------------------- Chicago / IEEE --


def _text(entry) -> str:
    return "".join(seg.text for seg in entry)


def test_unsupported_style_still_rejected():
    with pytest.raises(ValueError, match="Unsupported citation style"):
        build_citation_context([FakeRef(title="A Paper")], style="MLA")


def test_style_name_is_case_insensitive():
    ctx = build_citation_context([FakeRef(title="A Paper", year=2023)], style="chicago")
    assert ctx.style == "CHICAGO"


def test_chicago_in_text_uses_and_and_no_comma():
    """Chicago author-date: '(Smith and Doe 2023)' -- APA's '&' and the
    comma before the year are both APA-specific."""
    ref = FakeRef(title="A Paper", year=2023, authors=[{"name": "Smith, J."}, {"name": "Doe, K."}])
    ctx = build_citation_context([ref], style="CHICAGO")
    assert ctx.in_text(ref.id) == "(Smith and Doe 2023)"


def test_chicago_three_authors_use_et_al_in_text():
    ref = FakeRef(
        title="A Paper",
        year=2023,
        authors=[{"name": "Smith, J."}, {"name": "Doe, K."}, {"name": "Lee, M."}],
    )
    ctx = build_citation_context([ref], style="CHICAGO")
    assert ctx.in_text(ref.id) == "(Smith et al. 2023)"


def test_chicago_entry_inverts_only_the_first_author():
    """Alphabetising needs the first author inverted; the rest read naturally."""
    ref = FakeRef(
        title="A Paper",
        year=2023,
        authors=[{"name": "Smith, J. A."}, {"name": "Doe, K."}],
        source_title="Nature",
    )
    ctx = build_citation_context([ref], style="CHICAGO")
    entry = _text(ctx.entry(ref.id))
    assert entry.startswith("Smith, J. A., and K. Doe. 2023.")
    assert "“A Paper.”" in entry


def test_chicago_does_not_double_a_period_after_an_abbreviated_journal():
    ref = FakeRef(
        title="A Paper", year=2023, authors=[{"name": "Smith, J."}],
        source_title="IEEE Trans. Biomed. Eng.",
    )
    entry = _text(build_citation_context([ref], style="CHICAGO").entry(ref.id))
    assert "Eng.." not in entry
    assert "Eng." in entry


def test_ieee_in_text_is_a_bracketed_number_in_supply_order():
    first = FakeRef(title="Zebra Paper", year=2023, authors=[{"name": "Zulu, A."}])
    second = FakeRef(title="Alpha Paper", year=2021, authors=[{"name": "Adams, B."}])
    ctx = build_citation_context([first, second], style="IEEE")
    # Numbered by order supplied, NOT alphabetised the way APA/Chicago are.
    assert ctx.in_text(first.id) == "[1]"
    assert ctx.in_text(second.id) == "[2]"


def test_ieee_bibliography_keeps_numeric_order_not_alphabetical():
    first = FakeRef(title="Zebra Paper", year=2023, authors=[{"name": "Zulu, A."}])
    second = FakeRef(title="Alpha Paper", year=2021, authors=[{"name": "Adams, B."}])
    ctx = build_citation_context([first, second], style="IEEE")
    ordered = [rid for rid, _entry in ctx.bibliography()]
    assert ordered == [first.id, second.id]


def test_ieee_entry_puts_initials_before_surname():
    ref = FakeRef(
        title="A Paper", year=2023,
        authors=[{"name": "Smith, J. A."}, {"name": "Doe, K."}],
        source_title="Nature", doi="10.1/x",
    )
    entry = _text(build_citation_context([ref], style="IEEE").entry(ref.id))
    assert entry.startswith("[1] J. A. Smith and K. Doe, “A Paper,”")
    assert "[Online]. Available: https://doi.org/10.1/x" in entry


def test_ieee_truncates_beyond_six_authors():
    authors = [{"name": f"Author{i}, X."} for i in range(8)]
    ref = FakeRef(title="Many Authors", year=2023, authors=authors)
    entry = _text(build_citation_context([ref], style="IEEE").entry(ref.id))
    assert "et al." in entry
    assert "Author7" not in entry  # the 8th author must not be listed


def test_ieee_skips_year_letter_disambiguation():
    """Bracketed numbers already disambiguate, so '2024a'/'2024b' would be
    noise -- unlike APA/Chicago where the year *is* the identifier."""
    a = FakeRef(title="Alpha Study", year=2024, authors=[{"name": "Smith, J."}])
    b = FakeRef(title="Beta Study", year=2024, authors=[{"name": "Smith, J."}])
    ctx = build_citation_context([a, b], style="IEEE")
    assert "2024a" not in _text(ctx.entry(a.id))
    assert "2024b" not in _text(ctx.entry(b.id))


def test_apa_and_chicago_still_disambiguate_the_year():
    a = FakeRef(title="Alpha Study", year=2024, authors=[{"name": "Smith, J."}])
    b = FakeRef(title="Beta Study", year=2024, authors=[{"name": "Smith, J."}])
    for style, expected in (("APA", "(Smith, 2024a)"), ("CHICAGO", "(Smith 2024a)")):
        ctx = build_citation_context([a, b], style=style)
        assert ctx.in_text(a.id) == expected
