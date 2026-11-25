"""Comparison-only text normalization -- used exclusively to decide "does
this evidence span really appear in this paper text", never for display or
storage. The canonical keyword phrase (from app/data/sdg_goals.json) and
the original evidence text are always what gets persisted/rendered; this
module only powers the equality check in between.
"""

import re
import unicodedata

_CURLY_QUOTES = str.maketrans(
    {
        "‘": "'",  # left single quote
        "’": "'",  # right single quote
        "“": '"',  # left double quote
        "”": '"',  # right double quote
        "–": "-",  # en dash
        "—": "-",  # em dash
        "−": "-",  # minus sign
    }
)

_WHITESPACE_RUN = re.compile(r"\s+")


def normalize(text: str) -> str:
    """NFKC unicode normalization, curly quotes/dashes -> straight/hyphen,
    whitespace collapse, casefold. Two strings that read identically to a
    human -- differing only in which quote character a PDF export used, or
    how many spaces separate two words -- normalize to the same value.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_CURLY_QUOTES)
    text = _WHITESPACE_RUN.sub(" ", text)
    return text.strip().casefold()


def evidence_is_valid(evidence: str, paper_text: str) -> bool:
    """True iff `evidence` (verbatim, as claimed) really appears in
    `paper_text`, modulo the cosmetic differences normalize() irons out.
    Blank evidence is never valid -- an empty string is trivially "in"
    any text, which would make an empty claim look verified.
    """
    if not evidence or not evidence.strip():
        return False
    return normalize(evidence) in normalize(paper_text)
