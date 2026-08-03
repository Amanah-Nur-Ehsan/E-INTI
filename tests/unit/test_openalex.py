import httpx

from app.db.models.enums import EnrichmentProvider
from app.services.enrichment_types import RefIdentity
from app.services.openalex_service import OpenAlexService, _invert_abstract, _normalize_doi

WORK = {
    "doi": "https://doi.org/10.1016/j.example.2024.100001",
    "title": "Lightweight Fusion for Low-Resource Emotion Detection",
    "abstract_inverted_index": {
        "Machine": [0],
        "learning": [1],
        "improves": [2],
        "detection.": [3],
    },
    "publication_year": 2024,
    "authorships": [
        {"author": {"display_name": "Azhar M."}},
        {"author": {"display_name": "Amjad A."}},
    ],
    "primary_location": {"source": {"display_name": "Information (Switzerland)"}},
    "cited_by_count": 3,
    "type": "article",
}


def test_invert_abstract_reconstructs_word_order():
    assert _invert_abstract(WORK["abstract_inverted_index"]) == "Machine learning improves detection."


def test_invert_abstract_handles_missing_index():
    assert _invert_abstract(None) is None
    assert _invert_abstract({}) is None


def test_normalize_doi_strips_the_url_prefix():
    assert _normalize_doi("https://doi.org/10.1016/J.EXAMPLE.2024.100001") == (
        "10.1016/j.example.2024.100001"
    )
    assert _normalize_doi(None) is None


def test_fetch_single_lookup_builds_a_full_result():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/works/doi:10.1016/j.example.2024.100001"
        return httpx.Response(200, json=WORK)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.openalex.org")
    service = OpenAlexService(client=client)

    result = service.fetch(RefIdentity(title="x", doi="10.1016/j.example.2024.100001"))

    assert result is not None
    assert result.provider == EnrichmentProvider.OPENALEX
    assert result.abstract == "Machine learning improves detection."
    assert result.year == 2024
    assert result.doi == "10.1016/j.example.2024.100001"
    assert result.source_title == "Information (Switzerland)"
    assert [a["name"] for a in result.authors] == ["Azhar M.", "Amjad A."]
    assert result.citation_count == 3


def test_fetch_without_doi_returns_none():
    service = OpenAlexService(client=httpx.Client())
    assert service.fetch(RefIdentity(title="no doi here")) is None


def test_prefetch_populates_cache_and_fetch_reads_it_without_a_request():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert "filter" in request.url.params
        return httpx.Response(200, json={"results": [WORK]})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.openalex.org")
    service = OpenAlexService(client=client)

    service.prefetch([RefIdentity(title="x", doi="10.1016/j.example.2024.100001")])
    assert len(calls) == 1

    result = service.fetch(RefIdentity(title="x", doi="10.1016/j.example.2024.100001"))
    assert result is not None
    assert result.abstract == "Machine learning improves detection."
    # Still one call total -- fetch answered from the prefetched cache.
    assert len(calls) == 1


def test_prefetch_caches_a_miss_as_none_so_fetch_does_not_refetch():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.openalex.org")
    service = OpenAlexService(client=client)

    service.prefetch([RefIdentity(title="x", doi="10.1016/unresolvable")])
    assert service.fetch(RefIdentity(title="x", doi="10.1016/unresolvable")) is None
