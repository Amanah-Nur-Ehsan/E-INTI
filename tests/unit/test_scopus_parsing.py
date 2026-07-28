import json

import httpx
import pytest

from app.services.scopus_service import (
    ScopusService,
    _as_list,
    _dig,
    _unwrap,
    parse_abstract_response,
)
from tests.conftest import FIXTURES


def load(name: str) -> dict:
    return json.loads((FIXTURES / "scopus" / name).read_text())


def test_as_list_normalizes_collapsed_single_elements():
    assert _as_list([1, 2]) == [1, 2]
    assert _as_list({"a": 1}) == [{"a": 1}]
    assert _as_list(None) == []


def test_unwrap_handles_dollar_wrappers():
    assert _unwrap({"$": "fraud detection"}) == "fraud detection"
    assert _unwrap("plain") == "plain"
    assert _unwrap({"@href": "x"}) is None
    assert _unwrap(None) is None


def test_dig_tolerates_missing_and_list_levels():
    payload = {"a": [{"b": {"c": 42}}]}
    assert _dig(payload, "a", "b", "c") == 42
    assert _dig(payload, "a", "zzz", default="fallback") == "fallback"
    assert _dig(None, "a") is None


def test_parses_abstract_from_coredata():
    result = parse_abstract_response(load("10.1016_j.knosys.2021.100004.json"))
    assert "cost-sensitive" in result.abstract
    assert result.year == 2021
    assert result.source_title == "Knowledge-Based Systems"
    assert result.doi == "10.1016/j.knosys.2021.100004"
    assert result.author_keywords == ["class imbalance", "anomaly detection", "SMOTE"]
    assert result.subject_areas == ["Computer Science"]
    assert [a["name"] for a in result.authors] == ["Nakamura S.", "Ito, Kenji"]
    assert result.citation_count == 14


def test_parses_abstract_from_bibrecord_paragraphs():
    """No coredata description: the text lives in item.bibrecord.head.abstracts."""
    result = parse_abstract_response(load("10.1109_access.2020.100006.json"))
    assert result.abstract.startswith("Payment systems form dense transaction graphs")
    assert result.abstract.endswith("classifiers miss entirely.")
    # Single author and single keyword arrived as bare objects, not lists.
    assert [a["name"] for a in result.authors] == ["Garcia P."]
    assert result.author_keywords == ["graph neural networks"]


def test_parses_payload_without_keywords():
    result = parse_abstract_response(load("10.1016_j.patrec.2021.100009.json"))
    assert result.abstract.startswith("Accuracy is misleading")
    assert result.author_keywords == []
    assert result.index_keywords == []


def test_parses_empty_payload_without_crashing():
    result = parse_abstract_response({"abstracts-retrieval-response": {}})
    assert result.abstract is None
    assert result.authors == []
    assert result.year is None
    assert not result.has_abstract


def test_auth_error_disables_provider_but_returns_none():
    """A bad key must not fail the row — it falls through to the next provider."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid key"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.elsevier.com")
    service = ScopusService(client=client)

    from app.services.enrichment_types import RefIdentity

    assert service.fetch(RefIdentity(title="T", doi="10.1016/x")) is None
    assert service._disabled_reason is not None
    # Subsequent calls short-circuit without another request.
    assert service.fetch(RefIdentity(title="T2", doi="10.1016/y")) is None


def test_retries_then_succeeds_after_rate_limit():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(
            200,
            json={
                "abstracts-retrieval-response": {
                    "coredata": {"dc:title": "T", "dc:description": "An abstract."}
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.elsevier.com")
    service = ScopusService(client=client)

    from app.services.enrichment_types import RefIdentity

    result = service.fetch(RefIdentity(title="T", doi="10.1016/x"))
    assert result is not None
    assert result.abstract == "An abstract."
    assert calls["n"] == 2


def test_unentitled_full_view_downgrades_instead_of_disabling():
    """Keys without an institutional subscription still yield useful metadata."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        view = request.url.params.get("view")
        seen.append(view or "default")
        if view == "FULL":
            return httpx.Response(
                401,
                headers={"X-ELS-Status": "AUTHORIZATION_ERROR - not authorized for this view"},
                json={"service-error": {}},
            )
        return httpx.Response(
            200,
            json={
                "abstracts-retrieval-response": {
                    "coredata": {
                        "dc:title": "A Paper",
                        "prism:coverDate": "2021-01-01",
                        "prism:publicationName": "A Journal",
                    }
                }
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.elsevier.com"
    )
    service = ScopusService(client=client)

    from app.services.enrichment_types import RefIdentity

    result = service.fetch(RefIdentity(title="A Paper", doi="10.1016/x"))
    assert result is not None
    assert result.title == "A Paper"
    assert result.year == 2021
    # No abstract in the entitled view: the chain falls through to Semantic Scholar.
    assert not result.has_abstract
    assert service._disabled_reason is None
    assert seen == ["FULL", "default"]

    # The downgrade sticks, so later rows don't burn a request rediscovering it.
    service.fetch(RefIdentity(title="Another", doi="10.1016/y"))
    assert seen == ["FULL", "default", "default"]


def test_invalid_key_still_disables_the_provider():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, headers={"X-ELS-Status": "APIKEY_INVALID"}, json={})

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.elsevier.com"
    )
    service = ScopusService(client=client)

    from app.services.enrichment_types import RefIdentity

    assert service.fetch(RefIdentity(title="T", doi="10.1016/x")) is None
    assert "APIKEY_INVALID" in service._disabled_reason


def test_404_returns_none():
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(404)),
        base_url="https://api.elsevier.com",
    )
    from app.services.enrichment_types import RefIdentity

    assert ScopusService(client=client).fetch(RefIdentity(title="T", doi="10.1016/x")) is None


@pytest.mark.parametrize("identifier", ["2-s2.0-85100000002", "10.1016/j.eswa.2024.100001"])
def test_mock_scopus_serves_or_synthesizes(identifier):
    from app.services.enrichment_types import RefIdentity
    from app.services.mocks.mock_scopus import MockScopusService

    result = MockScopusService().fetch(RefIdentity(title="Some Paper Title", doi=identifier))
    assert result is not None and result.has_abstract


def test_mock_scopus_misses_notfound_dois():
    from app.services.enrichment_types import RefIdentity
    from app.services.mocks.mock_scopus import MockScopusService

    ref = RefIdentity(title="Unindexed", doi="10.9999/notfound.2019.000011")
    assert MockScopusService().fetch(ref) is None
