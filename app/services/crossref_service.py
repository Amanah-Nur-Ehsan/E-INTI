"""Crossref fallback — bibliographic metadata only.

Crossref abstracts are JATS-XML fragments and are absent for most records,
so this provider never supplies an abstract. A reference that only reaches
Crossref stays INCOMPLETE, per the spec's no-hallucinated-support rule.
"""

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models.enums import EnrichmentProvider
from app.services.enrichment_types import EnrichmentResult, RefIdentity

log = get_logger(__name__)

BASE_URL = "https://api.crossref.org"


class CrossrefService:
    name = "crossref"
    #: Crossref never returns a usable abstract, so the enrichment stage only
    #: consults it for references still missing basic bibliographic metadata.
    supplies_abstracts = False

    def __init__(self, client: httpx.Client | None = None, mailto: str | None = None):
        mailto = mailto or get_settings().enrichment_contact_email
        self._client = client or httpx.Client(
            base_url=BASE_URL,
            timeout=30.0,
            headers={"User-Agent": f"CitationINTI (mailto:{mailto})"},
        )
        self._mailto = mailto

    def close(self) -> None:
        self._client.close()

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        wait=wait_exponential(multiplier=2, max=60),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _get(self, path: str) -> dict | None:
        response = self._client.get(path, params={"mailto": self._mailto})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def fetch(self, ref: RefIdentity) -> EnrichmentResult | None:
        if not ref.doi:
            return None
        try:
            payload = self._get(f"/works/{ref.doi}")
        except httpx.HTTPStatusError as exc:
            log.warning("crossref_http_error", doi=ref.doi, status=exc.response.status_code)
            return None
        if not payload:
            return None

        message = payload.get("message") or {}
        titles = message.get("title") or []
        containers = message.get("container-title") or []
        date_parts = (message.get("issued") or {}).get("date-parts") or [[]]
        year = date_parts[0][0] if date_parts and date_parts[0] else None

        authors = []
        for author in message.get("author") or []:
            family = author.get("family")
            given = author.get("given")
            if family and given:
                authors.append({"name": f"{family}, {given}"})
            elif family or author.get("name"):
                authors.append({"name": family or author["name"]})

        return EnrichmentResult(
            provider=EnrichmentProvider.CROSSREF,
            title=titles[0] if titles else None,
            abstract=None,  # deliberately never trusted
            authors=authors,
            year=year,
            source_title=containers[0] if containers else None,
            doi=(message.get("DOI") or "").lower() or None,
            citation_count=message.get("is-referenced-by-count"),
            document_type=message.get("type"),
            publisher_url=message.get("URL"),
        )
