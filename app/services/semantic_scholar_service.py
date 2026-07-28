"""Semantic Scholar fallback — metadata *and* abstract when Scopus misses."""

import time

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.logging import get_logger
from app.db.models.enums import EnrichmentProvider
from app.services.enrichment_types import EnrichmentResult, RateLimited, RefIdentity

log = get_logger(__name__)

BASE_URL = "https://api.semanticscholar.org"
FIELDS = "title,abstract,year,authors,venue,externalIds,citationCount,publicationTypes"
#: Unauthenticated Graph API allows roughly 1 request/second.
MIN_SECONDS_BETWEEN_REQUESTS = 1.0


class SemanticScholarService:
    name = "semantic_scholar"

    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(base_url=BASE_URL, timeout=30.0)
        self._last_request_at = 0.0

    def close(self) -> None:
        self._client.close()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, RateLimited)),
        wait=wait_exponential(multiplier=2, max=60),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _get(self, path: str) -> dict | None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
            time.sleep(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)

        response = self._client.get(path, params={"fields": FIELDS})
        self._last_request_at = time.monotonic()

        if response.status_code == 429:
            raise RateLimited()
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def fetch(self, ref: RefIdentity) -> EnrichmentResult | None:
        if ref.doi:
            key = f"DOI:{ref.doi}"
        elif ref.semantic_scholar_id:
            key = ref.semantic_scholar_id
        else:
            return None

        try:
            payload = self._get(f"/graph/v1/paper/{key}")
        except httpx.HTTPStatusError as exc:
            log.warning("s2_http_error", key=key, status=exc.response.status_code)
            return None
        if not payload:
            return None

        external = payload.get("externalIds") or {}
        publication_types = payload.get("publicationTypes") or []
        return EnrichmentResult(
            provider=EnrichmentProvider.SEMANTIC_SCHOLAR,
            title=payload.get("title"),
            abstract=payload.get("abstract"),
            authors=[{"name": a.get("name")} for a in payload.get("authors") or [] if a.get("name")],
            year=payload.get("year"),
            source_title=payload.get("venue"),
            doi=(external.get("DOI") or "").lower() or None,
            semantic_scholar_id=payload.get("paperId"),
            citation_count=payload.get("citationCount"),
            document_type=publication_types[0] if publication_types else None,
        )
