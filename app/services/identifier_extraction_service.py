"""Pull DOI / Scopus EID / Semantic Scholar ids out of dataset LINK values.

The LINK column is whatever the researcher pasted: a Scopus record URL, a
doi.org URL, a bare DOI, a publisher landing page, or a Semantic Scholar
page. Explicit DOI/EID columns, when present, always win over parsing.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import unquote

#: DOIs are 10.<registrant>/<suffix>; the suffix runs to whitespace or a URL delimiter.
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>&]+", re.IGNORECASE)
EID_RE = re.compile(r"2-s2\.0-\d+", re.IGNORECASE)
S2_HASH_RE = re.compile(r"semanticscholar\.org/paper/(?:[^/\s]+/)?([0-9a-f]{40})", re.IGNORECASE)
SCOPUS_ID_RE = re.compile(r"[?&]scp=(\d+)", re.IGNORECASE)

#: Trailing characters that are punctuation of the sentence, not the DOI.
_DOI_TRAILING = ".,;:)]}>\"'"


class LinkKind(StrEnum):
    SCOPUS = "SCOPUS"
    DOI = "DOI"
    SEMANTIC_SCHOLAR = "SEMANTIC_SCHOLAR"
    PUBLISHER = "PUBLISHER"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ExtractedIdentifiers:
    doi: str | None = None
    scopus_eid: str | None = None
    scopus_id: str | None = None
    semantic_scholar_id: str | None = None
    kind: LinkKind = LinkKind.UNKNOWN

    @property
    def has_any(self) -> bool:
        return any([self.doi, self.scopus_eid, self.scopus_id, self.semantic_scholar_id])


def normalize_doi(raw: str | None) -> str | None:
    """Return a bare lowercase DOI, or None if the text holds no DOI."""
    if not raw:
        return None
    match = DOI_RE.search(unquote(str(raw)))
    if not match:
        return None
    doi = match.group(0).rstrip(_DOI_TRAILING)
    return doi.lower() or None


def extract_identifiers(
    link: str | None,
    doi_column: str | None = None,
    eid_column: str | None = None,
) -> ExtractedIdentifiers:
    doi = normalize_doi(doi_column)
    eid = None
    if eid_column:
        eid_match = EID_RE.search(str(eid_column))
        eid = eid_match.group(0).lower() if eid_match else None

    text = unquote(str(link)) if link else ""
    lowered = text.lower()

    if eid is None:
        eid_match = EID_RE.search(text)
        eid = eid_match.group(0).lower() if eid_match else None
    if doi is None:
        doi = normalize_doi(text)

    scopus_id_match = SCOPUS_ID_RE.search(text)
    s2_match = S2_HASH_RE.search(text)

    if eid or "scopus.com" in lowered:
        kind = LinkKind.SCOPUS
    elif s2_match:
        kind = LinkKind.SEMANTIC_SCHOLAR
    elif "doi.org" in lowered:
        kind = LinkKind.DOI
    elif doi:
        kind = LinkKind.PUBLISHER if text.startswith("http") else LinkKind.DOI
    elif text.startswith("http"):
        kind = LinkKind.PUBLISHER
    else:
        kind = LinkKind.UNKNOWN

    return ExtractedIdentifiers(
        doi=doi,
        scopus_eid=eid,
        scopus_id=scopus_id_match.group(1) if scopus_id_match else None,
        semantic_scholar_id=s2_match.group(1).lower() if s2_match else None,
        kind=kind,
    )
