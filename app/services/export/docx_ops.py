"""Low-level oxml primitives for inserting citations into a DOCX.

No business logic lives here — just run splitting, formatting-preserving
clones, and tracked-change wrapping. `docx_writer.py` decides *what* to
insert; this module only knows *how*.

`paragraph.text = "..."` never appears anywhere in this file or its
callers — that assignment destroys every run's formatting. Everything
here operates on `<w:r>` elements directly.
"""

import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from app.services.draft_parser_service import Block, _para_text, normalize_with_map

#: Sentence-terminal punctuation and closing quotes to insert *before*, so
#: a citation reads "...evidence (Smith, 2023)." rather than landing after
#: the full stop. Deliberately excludes ")" and "]": those close an existing
#: bracketed/parenthetical citation ("[1]", "(Smith, 2024)") that is part of
#: the sentence's content, not trailing decoration — "shown [1]." gets its
#: new citation inserted after "[1]", not between "]" and ".".
_TRAILING_PUNCTUATION = re.compile(r"[.?!…\"'”’]+$")

#: Tracked-change revision ids start well above any id a real Word editing
#: session is likely to have produced, so a document that already carries
#: revisions never collides with ours.
_REVISION_ID_BASE = 900_000


@dataclass(frozen=True)
class InsertionPoint:
    """Where to splice new content into an existing paragraph."""

    paragraph: object  # docx.text.paragraph.Paragraph
    run_element: object  # the <w:r> (or its <w:ins> ancestor) to split at
    offset_in_run: int  # 0..len(run_element.text)


def find_insertion_offset(normalized: str, sentence_start: int, sentence_end: int) -> int:
    """The normalized-text index to insert *before* — after any trailing
    sentence punctuation, so a citation lands inside the sentence rather
    than after its full stop.
    """
    sentence = normalized[sentence_start:sentence_end]
    match = _TRAILING_PUNCTUATION.search(sentence)
    if match:
        return sentence_start + match.start()
    return sentence_end


def resolve_insertion_point(
    document,
    flat_paragraphs: list,
    block: Block,
    claim_char_start: int,
    claim_char_end: int,
    expected_sentence: str,
) -> InsertionPoint | None:
    """Locate where a claim's citation belongs inside the source docx.

    Returns None — a POSITION_MISMATCH — rather than guessing, whenever the
    live paragraph text no longer matches what was stored at analysis time.
    The caller is responsible for recording that outcome; this function
    never inserts anything and never raises for a mismatch.
    """
    if block.paragraph_index >= len(flat_paragraphs):
        return None
    paragraph = flat_paragraphs[block.paragraph_index]

    normalized, src = normalize_with_map(_para_text(paragraph))
    if normalized != block.text:
        return None  # the paragraph itself has changed since analysis

    s0 = claim_char_start - block.char_start
    s1 = claim_char_end - block.char_start
    if not (0 <= s0 <= s1 <= len(normalized)):
        return None
    if normalized[s0:s1] != expected_sentence:
        return None  # the sentence text within the paragraph has changed

    insert_at = find_insertion_offset(normalized, s0, s1)
    raw_offset = src[insert_at] if insert_at < len(src) else (src[-1] + 1 if src else 0)

    cumulative = 0
    for run_el in paragraph._p.xpath(".//w:r[not(ancestor::w:del)]"):
        run_text = _run_text(run_el)
        run_len = len(run_text)
        if raw_offset <= cumulative + run_len:
            return InsertionPoint(
                paragraph=paragraph, run_element=run_el, offset_in_run=raw_offset - cumulative
            )
        cumulative += run_len

    return None  # offset fell past the end of every run — treat as mismatch


def _run_text(run_el) -> str:
    parts = []
    for t in run_el.findall(qn("w:t")):
        parts.append(t.text or "")
    for _ in run_el.findall(qn("w:tab")):
        parts.append("\t")
    for _ in run_el.findall(qn("w:br")) + run_el.findall(qn("w:cr")):
        parts.append("\n")
    return "".join(parts)


def _set_text(run_el, text: str) -> None:
    for t in run_el.findall(qn("w:t")):
        run_el.remove(t)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    run_el.append(t)


def clone_run_formatting(source_run_el, text: str):
    """A new `<w:r>` carrying a deep copy of the source run's `<w:rPr>` —
    bold, italic, font, and colour all travel with it.
    """
    new_run = OxmlElement("w:r")
    rpr = source_run_el.find(qn("w:rPr"))
    if rpr is not None:
        new_run.append(deepcopy(rpr))
    _set_text(new_run, text)
    return new_run


def _anchor(run_el):
    """A `<w:ins>` may not nest inside another `<w:ins>`; if the target run
    already sits inside one (i.e. this paragraph carries earlier tracked
    changes), hoist the insertion point to that ancestor instead.
    """
    parent = run_el.getparent()
    if parent is not None and parent.tag == qn("w:ins"):
        return parent
    return run_el


def insert_node_at(point: InsertionPoint, node) -> None:
    """Splice `node` into the paragraph at `point`, splitting the target
    run if the offset falls strictly inside it.

    Exports always start from the pristine uploaded file (never a previous
    export — see the module docstring), so the run being split here is
    never itself already inside a `<w:ins>`; the `_anchor` hoist only
    matters for the boundary cases (`<=0` / `>=len`), where a citation
    lands immediately next to an existing tracked change.
    """
    run_el = point.run_element
    original = _run_text(run_el)

    if point.offset_in_run <= 0:
        _anchor(run_el).addprevious(node)
    elif point.offset_in_run >= len(original):
        _anchor(run_el).addnext(node)
    else:
        tail = deepcopy(run_el)
        _set_text(tail, original[point.offset_in_run :])
        _set_text(run_el, original[: point.offset_in_run])
        # Two addnext calls after run_el, each inserting immediately after
        # it: first the tail becomes run_el's neighbour, then node is
        # spliced between them — final order is run_el, node, tail.
        run_el.addnext(tail)
        run_el.addnext(node)


def wrap_tracked_insert(run_el, *, author: str, when: datetime | None, revision_id: int):
    """Wrap a `<w:r>` (or several) in a `<w:ins>` so Word shows it as a
    reviewable tracked-change insertion rather than plain text.

    Always call this on the *newly created* run from `clone_run_formatting`
    — never on the paragraph's existing run that `resolve_insertion_point`
    targeted. Wrapping detaches the element from its current parent, and
    `insert_node_at` needs the target run still attached to the paragraph
    to compute a valid anchor.
    """
    ins = OxmlElement("w:ins")
    ins.set(qn("w:id"), str(_REVISION_ID_BASE + revision_id))
    ins.set(qn("w:author"), author)
    ins.set(qn("w:date"), (when or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    ins.append(run_el)
    return ins
