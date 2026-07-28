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


#: The batch endpoint accepts many ids per request. Chunking here turns a
#: 6,000-row dataset from ~1.7 hours of single lookups into a handful of calls.
BATCH_SIZE = 400
#: The batch endpoint rate-limits aggressively; pace chunks and retry on 429.
BATCH_PAUSE_SECONDS = 3.0
BATCH_MAX_ATTEMPTS = 5


class SemanticScholarService:
    name = "semantic_scholar"

    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(base_url=BASE_URL, timeout=120.0)
        self._last_request_at = 0.0
        self._prefetched: dict[str, EnrichmentResult | None] = {}

    def close(self) -> None:
        self._client.close()

    def prefetch(self, refs: list[RefIdentity]) -> None:
        """Resolve many references in bulk before the per-row chain runs.

        Populates an in-process cache that `fetch` reads first; anything the
        batch endpoint does not return simply falls through to a single lookup.
        """
        dois = sorted({r.doi for r in refs if r.doi})
        if not dois:
            return

        for start in range(0, len(dois), BATCH_SIZE):
            chunk = dois[start : start + BATCH_SIZE]
            payloads = self._post_batch(chunk)
            if payloads is None:
                # Chunk exhausted its retries; these DOIs fall through to
                # single lookups rather than being treated as unresolvable.
                continue

            for doi, payload in zip(chunk, payloads, strict=False):
                self._prefetched[doi] = self._to_result(payload) if payload else None

            resolved = sum(1 for d in chunk if self._prefetched.get(d))
            log.info(
                "s2_batch_prefetched",
                chunk=len(chunk),
                resolved=resolved,
                cached=len(self._prefetched),
                total=len(dois),
            )
            time.sleep(BATCH_PAUSE_SECONDS)

    def _post_batch(self, chunk: list[str]) -> list | None:
        """POST one chunk, backing off on the 429s this endpoint returns freely."""
        delay = BATCH_PAUSE_SECONDS
        for attempt in range(1, BATCH_MAX_ATTEMPTS + 1):
            try:
                response = self._client.post(
                    "/graph/v1/paper/batch",
                    params={"fields": FIELDS},
                    json={"ids": [f"DOI:{doi}" for doi in chunk]},
                )
            except Exception as exc:
                log.warning("s2_batch_error", error=str(exc), attempt=attempt)
                time.sleep(delay)
                delay *= 2
                continue

            if response.status_code == 200:
                return response.json()
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else delay
                log.info("s2_batch_rate_limited", attempt=attempt, sleeping_for=round(wait, 1))
                time.sleep(wait)
                delay = min(delay * 2, 30.0)
                continue

            log.warning("s2_batch_failed", status=response.status_code, attempt=attempt)
            return None

        log.warning("s2_batch_exhausted", chunk=len(chunk))
        return None

    @staticmethod
    def _to_result(payload: dict) -> EnrichmentResult:
        external = payload.get("externalIds") or {}
        publication_types = payload.get("publicationTypes") or []
        return EnrichmentResult(
            provider=EnrichmentProvider.SEMANTIC_SCHOLAR,
            title=payload.get("title"),
            abstract=payload.get("abstract"),
            authors=[
                {"name": a.get("name")} for a in payload.get("authors") or [] if a.get("name")
            ],
            year=payload.get("year"),
            source_title=payload.get("venue"),
            doi=(external.get("DOI") or "").lower() or None,
            semantic_scholar_id=payload.get("paperId"),
            citation_count=payload.get("citationCount"),
            document_type=publication_types[0] if publication_types else None,
        )

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
        if ref.doi and ref.doi in self._prefetched:
            return self._prefetched[ref.doi]

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
        return self._to_result(payload)
