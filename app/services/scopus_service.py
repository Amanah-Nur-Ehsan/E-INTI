"""Elsevier Scopus Abstract Retrieval client.

Two things make this messy and both are handled by tolerant helpers rather
than strict models:

1. Elsevier collapses single-element arrays into bare objects, so any list
   field may arrive as a dict (`_as_list`).
2. Text values are frequently wrapped as ``{"$": "value"}`` (`_unwrap`).

The abstract itself lives in one of two places depending on entitlement,
so `parse_abstract_response` checks both.
"""

import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models.enums import EnrichmentProvider
from app.services.enrichment_types import (
    EnrichmentResult,
    ProviderAuthError,
    RateLimited,
    RefIdentity,
)

log = get_logger(__name__)

BASE_URL = "https://api.elsevier.com"
#: Abstract Retrieval quota class allows ~9 req/s; stay well under it.
MIN_SECONDS_BETWEEN_REQUESTS = 0.25
#: When this few requests remain in the weekly quota, wait for the reset.
RATE_LIMIT_FLOOR = 5


def _as_list(value: Any) -> list:
    """Normalize Elsevier's list-or-single-object fields to a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _unwrap(value: Any) -> str | None:
    """Pull text out of ``{"$": "..."}`` wrappers and plain strings alike."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in ("$", "#text", "value"):
            if key in value:
                return _unwrap(value[key])
    return None


def _dig(obj: Any, *path: str, default: Any = None) -> Any:
    """Walk nested dicts, tolerating missing keys and list-wrapped levels."""
    current = obj
    for key in path:
        if isinstance(current, list):
            current = current[0] if current else None
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def _to_int(value: Any) -> int | None:
    text = _unwrap(value)
    if text is None:
        return None
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


def _author_name(author: dict) -> str | None:
    name = _unwrap(author.get("ce:indexed-name")) or _unwrap(author.get("preferred-name"))
    if name:
        return name
    surname = _unwrap(author.get("ce:surname"))
    given = _unwrap(author.get("ce:given-name")) or _unwrap(author.get("ce:initials"))
    if surname and given:
        return f"{surname}, {given}"
    return surname or given


def parse_abstract_response(payload: dict) -> EnrichmentResult:
    """Map an abstracts-retrieval-response document onto EnrichmentResult."""
    root = payload.get("abstracts-retrieval-response", payload)
    core = _dig(root, "coredata", default={}) or {}

    abstract = _unwrap(core.get("dc:description"))
    if not abstract:
        # Full-view responses can instead carry the abstract in the bibrecord.
        raw = _dig(root, "item", "bibrecord", "head", "abstracts")
        abstract = _unwrap(raw)
        if abstract is None and isinstance(raw, dict):
            paragraphs = _as_list(_dig(raw, "abstract", "ce:para"))
            joined = " ".join(filter(None, (_unwrap(p) for p in paragraphs)))
            abstract = joined or None

    authors = []
    for author in _as_list(_dig(root, "authors", "author")):
        if not isinstance(author, dict):
            continue
        name = _author_name(author)
        if name:
            authors.append({"name": name, "scopus_author_id": author.get("@auid")})

    author_keywords = []
    for keyword in _as_list(_dig(root, "authkeywords", "author-keyword")):
        text = _unwrap(keyword)
        if text:
            author_keywords.append(text)

    index_keywords = []
    for group in _as_list(_dig(root, "idxterms", "mainterm")):
        text = _unwrap(group)
        if text:
            index_keywords.append(text)

    subject_areas = []
    for area in _as_list(_dig(root, "subject-areas", "subject-area")):
        text = _unwrap(area)
        if text:
            subject_areas.append(text)

    cover_date = _unwrap(core.get("prism:coverDate")) or ""
    year = int(cover_date[:4]) if cover_date[:4].isdigit() else None

    links = {link.get("@rel"): link.get("@href") for link in _as_list(core.get("link")) if isinstance(link, dict)}

    return EnrichmentResult(
        provider=EnrichmentProvider.SCOPUS,
        title=_unwrap(core.get("dc:title")),
        abstract=abstract,
        authors=authors,
        year=year,
        source_title=_unwrap(core.get("prism:publicationName")),
        doi=(_unwrap(core.get("prism:doi")) or "").lower() or None,
        scopus_eid=_unwrap(core.get("eid")),
        scopus_id=(_unwrap(core.get("dc:identifier")) or "").replace("SCOPUS_ID:", "") or None,
        author_keywords=author_keywords,
        index_keywords=index_keywords,
        subject_areas=subject_areas,
        citation_count=_to_int(core.get("citedby-count")),
        document_type=_unwrap(core.get("subtypeDescription")),
        scopus_url=links.get("scopus"),
        publisher_url=links.get("full-text") or _unwrap(core.get("prism:url")),
    )


class ScopusService:
    """Sync client (worker-side). One instance per worker process."""

    name = "scopus"

    def __init__(self, client: httpx.Client | None = None):
        settings = get_settings()
        headers = {
            "X-ELS-APIKey": settings.elsevier_api_key,
            "Accept": "application/json",
        }
        if settings.elsevier_inst_token:
            headers["X-ELS-Insttoken"] = settings.elsevier_inst_token
        self._client = client or httpx.Client(base_url=BASE_URL, headers=headers, timeout=30.0)
        self._last_request_at = 0.0
        self._disabled_reason: str | None = None

    def close(self) -> None:
        self._client.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
            time.sleep(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)

    def _observe_rate_limit(self, response: httpx.Response) -> None:
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")
        if remaining is None:
            return
        try:
            remaining_n = int(remaining)
        except ValueError:
            return
        if remaining_n <= RATE_LIMIT_FLOOR and reset:
            try:
                wait_for = max(0.0, float(reset) - time.time())
            except ValueError:
                return
            log.warning("scopus_quota_low", remaining=remaining_n, sleeping_for=round(wait_for, 1))
            time.sleep(min(wait_for, 60.0))

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, RateLimited)),
        wait=wait_exponential(multiplier=2, max=120),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _get(self, path: str) -> dict | None:
        self._throttle()
        response = self._client.get(path, params={"view": "FULL"})
        self._last_request_at = time.monotonic()

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimited(float(retry_after) if retry_after else None)
        if response.status_code in (401, 403):
            raise ProviderAuthError(f"Scopus rejected credentials ({response.status_code})")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        self._observe_rate_limit(response)
        return response.json()

    def fetch(self, ref: RefIdentity) -> EnrichmentResult | None:
        if self._disabled_reason:
            return None

        attempts: list[str] = []
        if ref.scopus_eid:
            attempts.append(f"/content/abstract/eid/{ref.scopus_eid}")
        if ref.doi:
            attempts.append(f"/content/abstract/doi/{ref.doi}")

        for path in attempts:
            try:
                payload = self._get(path)
            except ProviderAuthError as exc:
                # Bad key: the whole provider is unusable, but individual rows
                # should still fall through to Semantic Scholar / Crossref.
                self._disabled_reason = str(exc)
                log.error("scopus_disabled", reason=str(exc))
                return None
            except httpx.HTTPStatusError as exc:
                log.warning("scopus_http_error", path=path, status=exc.response.status_code)
                continue
            if payload:
                return parse_abstract_response(payload)
        return None
