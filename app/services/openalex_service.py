"""OpenAlex fallback — free, no API key, batched abstract recovery.

Runs after Semantic Scholar in the chain: OpenAlex's coverage overlaps
Semantic Scholar's but isn't a subset of it, so a reference that misses
Scopus (no abstract entitlement) and Semantic Scholar (not indexed there)
still has a real chance here. Measured against this library's actual
backlog of abstract-less references: OpenAlex has a usable abstract for
roughly a quarter of them.

Abstracts come back as an "inverted index" (word -> list of positions)
rather than plain text -- a deliberate space-saving choice on OpenAlex's
side, not something specific to any one paper -- so `_invert_abstract`
reconstructs the sentence from position order before it's trusted.
"""

import time

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.logging import get_logger
from app.db.models.enums import EnrichmentProvider
from app.services.enrichment_types import EnrichmentResult, RateLimited, RefIdentity

log = get_logger(__name__)

BASE_URL = "https://api.openalex.org"
SELECT_FIELDS = (
    "doi,title,abstract_inverted_index,publication_year,authorships,"
    "primary_location,cited_by_count,type"
)
#: The polite pool (a mailto param) gets a much higher rate limit than
#: anonymous requests; this is not a credential, just good-citizen contact info.
CONTACT_EMAIL = "citationinti@example.org"

#: filter=doi:a|b|c accepts many values per request -- batching turns a
#: multi-thousand-row backlog into a handful of requests instead of one per row.
BATCH_SIZE = 50
BATCH_PAUSE_SECONDS = 0.15


def _invert_abstract(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    positions: dict[int, str] = {}
    for word, places in index.items():
        for place in places:
            positions[place] = word
    if not positions:
        return None
    return " ".join(positions[i] for i in sorted(positions))


class OpenAlexService:
    name = "openalex"

    def __init__(self, client: httpx.Client | None = None, mailto: str = CONTACT_EMAIL):
        self._client = client or httpx.Client(base_url=BASE_URL, timeout=60.0)
        self._mailto = mailto
        self._prefetched: dict[str, EnrichmentResult | None] = {}

    def close(self) -> None:
        self._client.close()

    def prefetch(self, refs: list[RefIdentity]) -> None:
        """Resolve many DOIs in bulk before the per-row chain runs.

        Anything the batch doesn't resolve simply falls through to `fetch`'s
        single-lookup path rather than being treated as unresolvable.
        """
        dois = sorted({r.doi for r in refs if r.doi})
        if not dois:
            return

        for start in range(0, len(dois), BATCH_SIZE):
            chunk = dois[start : start + BATCH_SIZE]
            works = self._get_batch(chunk)
            if works is None:
                continue

            by_doi = {}
            for work in works:
                doi = _normalize_doi(work.get("doi"))
                if doi:
                    by_doi[doi] = work
            for doi in chunk:
                work = by_doi.get(doi)
                self._prefetched[doi] = self._to_result(work) if work else None

            log.info(
                "openalex_batch_prefetched",
                chunk=len(chunk),
                resolved=sum(1 for d in chunk if self._prefetched.get(d)),
                cached=len(self._prefetched),
                total=len(dois),
            )
            time.sleep(BATCH_PAUSE_SECONDS)

    def _get_batch(self, chunk: list[str]) -> list[dict] | None:
        filt = "doi:" + "|".join(chunk)
        try:
            response = self._request(
                "/works", params={"filter": filt, "per-page": len(chunk), "select": SELECT_FIELDS}
            )
        except Exception as exc:
            log.warning("openalex_batch_error", error=str(exc), chunk=len(chunk))
            return None
        return response.get("results") if response else None

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, RateLimited)),
        wait=wait_exponential(multiplier=2, max=60),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _request(self, path: str, params: dict) -> dict | None:
        response = self._client.get(path, params={**params, "mailto": self._mailto})
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimited(retry_after=float(retry_after) if retry_after else None)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def fetch(self, ref: RefIdentity) -> EnrichmentResult | None:
        if not ref.doi:
            return None
        if ref.doi in self._prefetched:
            return self._prefetched[ref.doi]

        try:
            payload = self._request(
                f"/works/doi:{ref.doi}", params={"select": SELECT_FIELDS}
            )
        except httpx.HTTPStatusError as exc:
            log.warning("openalex_http_error", doi=ref.doi, status=exc.response.status_code)
            return None
        if not payload:
            return None
        return self._to_result(payload)

    @staticmethod
    def _to_result(payload: dict) -> EnrichmentResult:
        authorships = payload.get("authorships") or []
        authors = [
            {"name": a["author"]["display_name"]}
            for a in authorships
            if a.get("author", {}).get("display_name")
        ]
        source = (payload.get("primary_location") or {}).get("source") or {}
        return EnrichmentResult(
            provider=EnrichmentProvider.OPENALEX,
            title=payload.get("title"),
            abstract=_invert_abstract(payload.get("abstract_inverted_index")),
            authors=authors,
            year=payload.get("publication_year"),
            source_title=source.get("display_name"),
            doi=_normalize_doi(payload.get("doi")),
            citation_count=payload.get("cited_by_count"),
            document_type=payload.get("type"),
        )


def _normalize_doi(raw: str | None) -> str | None:
    """OpenAlex returns DOIs as full URLs (https://doi.org/10.x/y)."""
    if not raw:
        return None
    return raw.removeprefix("https://doi.org/").removeprefix("http://doi.org/").lower() or None
