"""Draft parsing and sentence segmentation.

The invariant everything downstream depends on: every char_start/char_end
indexes into `drafts.raw_text`, and `raw_text[start:end] == text` exactly.
To keep that true, each paragraph is normalized *before* its offset is
assigned, raw_text is assembled once, and spaCy runs per block so sentence
offsets compose additively onto the block offset.
"""

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Draft
from app.db.models.enums import ParseStatus

log = get_logger(__name__)

BLOCK_SEPARATOR = "\n\n"

#: Tokens after which a period does not end a sentence in academic prose.
ABBREVIATIONS = (
    "et al.",
    "e.g.",
    "i.e.",
    "cf.",
    "vs.",
    "viz.",
    "resp.",
    "approx.",
    "ca.",
    "Fig.",
    "Figs.",
    "Eq.",
    "Eqs.",
    "Ref.",
    "Refs.",
    "Tab.",
    "No.",
    "Sec.",
    "Ch.",
    "pp.",
    "Dr.",
    "Prof.",
    "Mr.",
    "Ms.",
    "St.",
)

_ABBREV_PATTERN = re.compile(
    r"(?:" + "|".join(re.escape(a) for a in ABBREVIATIONS) + r")$", re.IGNORECASE
)
#: A single capital letter followed by a period, i.e. an initial: "J. Smith".
_INITIAL_PATTERN = re.compile(r"\b[A-Z]\.$")
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class Block:
    """One paragraph of the draft, with its span in raw_text."""

    text: str
    char_start: int
    char_end: int
    paragraph_index: int
    section_title: str | None = None
    is_heading: bool = False


@dataclass
class Sentence:
    text: str
    char_start: int
    char_end: int
    paragraph_index: int
    sentence_index: int
    section_title: str | None = None


@dataclass
class ParsedDraft:
    raw_text: str
    blocks: list[Block] = field(default_factory=list)
    sentences: list[Sentence] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "blocks": [asdict(b) for b in self.blocks],
            "sentences": [asdict(s) for s in self.sentences],
        }


def normalize_paragraph(text: str) -> str:
    """Applied before offsets are assigned — never after."""
    text = text.replace(" ", " ").replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _assemble(raw_blocks: list[tuple[str, bool, str | None]]) -> ParsedDraft:
    """Build raw_text and block offsets in one pass.

    raw_blocks items are (text, is_heading, explicit_section_title).
    """
    pieces: list[str] = []
    blocks: list[Block] = []
    cursor = 0
    current_section: str | None = None

    for index, (text, is_heading, explicit_section) in enumerate(raw_blocks):
        normalized = normalize_paragraph(text)
        if not normalized:
            continue

        if cursor > 0:
            pieces.append(BLOCK_SEPARATOR)
            cursor += len(BLOCK_SEPARATOR)

        start = cursor
        pieces.append(normalized)
        cursor += len(normalized)

        if is_heading:
            current_section = normalized

        blocks.append(
            Block(
                text=normalized,
                char_start=start,
                char_end=cursor,
                paragraph_index=index,
                section_title=explicit_section or (normalized if is_heading else current_section),
                is_heading=is_heading,
            )
        )

    return ParsedDraft(raw_text="".join(pieces), blocks=blocks)


def parse_docx(path: Path) -> ParsedDraft:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(str(path))
    raw_blocks: list[tuple[str, bool, str | None]] = []

    def paragraph_entry(paragraph: Paragraph) -> tuple[str, bool, str | None]:
        style = (paragraph.style.name or "") if paragraph.style is not None else ""
        is_heading = style.startswith("Heading") or style == "Title"
        return paragraph.text, is_heading, None

    for paragraph in document.paragraphs:
        raw_blocks.append(paragraph_entry(paragraph))

    # Table cells carry real prose in some drafts; including them keeps
    # raw_text a faithful record of the document.
    for table in document.tables:
        if not isinstance(table, Table):
            continue
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    raw_blocks.append(paragraph_entry(paragraph))

    return _assemble(raw_blocks)


def parse_markdown(path: Path) -> ParsedDraft:
    raw_blocks: list[tuple[str, bool, str | None]] = []
    for chunk in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")):
        chunk = chunk.strip()
        if not chunk:
            continue
        heading = _MD_HEADING.match(chunk)
        if heading:
            raw_blocks.append((heading.group(2), True, None))
        else:
            raw_blocks.append((chunk.replace("\n", " "), False, None))
    return _assemble(raw_blocks)


def parse_plaintext(path: Path) -> ParsedDraft:
    raw_blocks = [
        (chunk.replace("\n", " "), False, None)
        for chunk in re.split(r"\n\s*\n", path.read_text(encoding="utf-8"))
        if chunk.strip()
    ]
    return _assemble(raw_blocks)


def parse_file(path: Path) -> ParsedDraft:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        parsed = parse_docx(path)
    elif suffix in (".md", ".markdown"):
        parsed = parse_markdown(path)
    elif suffix in (".txt", ".text"):
        parsed = parse_plaintext(path)
    else:
        raise ValueError(f"Unsupported draft format: {path.suffix}")

    parsed.sentences = segment(parsed)
    return parsed


@lru_cache
def get_nlp():
    import spacy
    from spacy.language import Language

    @Language.component("academic_sentence_fixer")
    def academic_sentence_fixer(doc):
        for index, token in enumerate(doc[:-1]):
            prefix = doc[: index + 1].text
            following = doc[index + 1]
            if _ABBREV_PATTERN.search(prefix) or _INITIAL_PATTERN.search(prefix):
                following.is_sent_start = False
            # "3.5 percent" — a period between digits is a decimal point.
            if token.text == "." and index > 0:
                if doc[index - 1].text.isdigit() and following.text[:1].isdigit():
                    following.is_sent_start = False
        return doc

    nlp = spacy.load(get_settings().spacy_model, exclude=["ner", "lemmatizer"])
    if "academic_sentence_fixer" not in nlp.pipe_names:
        nlp.add_pipe("academic_sentence_fixer", before="parser")
    return nlp


def segment(parsed: ParsedDraft) -> list[Sentence]:
    """Segment each block separately so offsets compose additively."""
    nlp = get_nlp()
    sentences: list[Sentence] = []

    body_blocks = [b for b in parsed.blocks if not b.is_heading]
    docs = nlp.pipe([b.text for b in body_blocks])

    for block, doc in zip(body_blocks, docs, strict=True):
        for sentence_index, sent in enumerate(doc.sents):
            text = sent.text.strip()
            if not text:
                continue
            # Re-anchor onto the block text to absorb spaCy's own whitespace trimming.
            offset = block.text.find(text, sent.start_char if sent.start_char < len(block.text) else 0)
            if offset < 0:
                offset = sent.start_char
            sentences.append(
                Sentence(
                    text=text,
                    char_start=block.char_start + offset,
                    char_end=block.char_start + offset + len(text),
                    paragraph_index=block.paragraph_index,
                    sentence_index=sentence_index,
                    section_title=block.section_title,
                )
            )

    return sentences


def local_context(sentences: list[Sentence], index: int) -> str:
    """Previous + current + next sentence — what retrieval actually queries on."""
    window = sentences[max(0, index - 1) : index + 2]
    return " ".join(s.text for s in window)


def parse_and_store_draft(session: Session, draft_id: uuid.UUID) -> dict:
    """Stage body: parse the uploaded file and persist text, blocks, sentences."""
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise ValueError(f"Draft {draft_id} not found")

    path = Path(draft.storage_path)
    if not path.exists():
        raise FileNotFoundError(f"Draft file missing: {path}")

    try:
        parsed = parse_file(path)
    except Exception as exc:
        draft.parse_status = ParseStatus.FAILED
        draft.parse_error = f"{type(exc).__name__}: {exc}"
        session.commit()
        raise

    draft.raw_text = parsed.raw_text
    draft.parsed_content = parsed.to_json()
    draft.parse_status = ParseStatus.PARSED
    draft.parse_error = None
    draft.parsed_at = datetime.now(UTC)
    session.commit()

    return {"blocks": len(parsed.blocks), "sentences": len(parsed.sentences)}
