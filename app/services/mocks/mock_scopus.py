"""Offline stand-in for the Scopus Abstract Retrieval API.

Fixture payloads go through the *real* parser, so mock mode still
exercises `parse_abstract_response`. DOIs containing "notfound" return a
miss so the INCOMPLETE path stays covered without real credentials.
"""

import hashlib
import json
from pathlib import Path

from app.core.logging import get_logger
from app.db.models.enums import EnrichmentProvider
from app.services.enrichment_types import EnrichmentResult, RefIdentity
from app.services.scopus_service import parse_abstract_response

log = get_logger(__name__)

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "scopus"


def fixture_name(identifier: str) -> str:
    return identifier.replace("/", "_").replace(":", "_").lower() + ".json"


class MockScopusService:
    name = "scopus(mock)"

    def __init__(self, fixture_dir: Path | None = None):
        self._fixture_dir = fixture_dir or FIXTURE_DIR

    def close(self) -> None:
        pass

    def _load_fixture(self, identifier: str) -> dict | None:
        path = self._fixture_dir / fixture_name(identifier)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def fetch(self, ref: RefIdentity) -> EnrichmentResult | None:
        for identifier in filter(None, (ref.scopus_eid, ref.doi)):
            if "notfound" in identifier.lower():
                return None
            payload = self._load_fixture(identifier)
            if payload is not None:
                return parse_abstract_response(payload)

        if not (ref.doi or ref.scopus_eid):
            return None

        return self._synthesize(ref)

    def _synthesize(self, ref: RefIdentity) -> EnrichmentResult:
        """Deterministic filler so unfixtured rows still enrich reproducibly."""
        seed = hashlib.sha256((ref.doi or ref.scopus_eid or ref.title).encode()).hexdigest()
        year = 2015 + int(seed[:2], 16) % 10
        keywords = [w.lower() for w in ref.title.split() if len(w) > 5][:4]
        return EnrichmentResult(
            provider=EnrichmentProvider.SCOPUS,
            title=ref.title,
            abstract=(
                f"This study investigates {ref.title.lower()}. The authors describe the "
                f"methodology, report empirical observations, and discuss implications for "
                f"related work in the field."
            ),
            authors=[{"name": "Mock, A."}],
            year=year,
            source_title="Mock Journal of Applied Research",
            doi=ref.doi,
            scopus_eid=ref.scopus_eid,
            author_keywords=keywords,
            citation_count=int(seed[2:4], 16),
            document_type="Article",
        )
