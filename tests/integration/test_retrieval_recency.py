"""vector_search must never surface a reference outside the configured
recency window (default: this year and the 4 before it), regardless of
how well it matches semantically -- this is an institutional rule, not a
ranking preference, so it's enforced in the SQL itself.
"""

from datetime import UTC, datetime

import pytest

from app.core.config import get_settings
from app.db.models import ReferencePaper
from app.services.embedding_service import fake_embed

pytestmark = pytest.mark.integration

SHARED_TEXT = "quantum annealing optimization for combinatorial scheduling problems"


def _make_reference(year: int | None, suffix: str) -> ReferencePaper:
    vector = fake_embed([SHARED_TEXT])[0]
    return ReferencePaper(
        title=f"Quantum annealing scheduling study {suffix}",
        abstract=SHARED_TEXT,
        year=year,
        embedding=vector.tolist(),
        content_hash=f"hash-{suffix}",
    )


async def test_vector_search_excludes_references_older_than_the_recency_window(db_session):
    from app.services.retrieval_service import vector_search

    current_year = datetime.now(UTC).year
    window = get_settings().citation_recency_years
    oldest_allowed = current_year - (window - 1)

    current = _make_reference(current_year, "current")
    edge = _make_reference(oldest_allowed, "edge")
    too_old = _make_reference(oldest_allowed - 1, "too-old")
    unknown_year = _make_reference(None, "unknown-year")

    db_session.add_all([current, edge, too_old, unknown_year])
    db_session.commit()

    query_vector = fake_embed([SHARED_TEXT])[0]
    results = vector_search(db_session, query_vector, limit=10)
    titles = {c.title for c in results}

    assert current.title in titles
    assert edge.title in titles
    assert too_old.title not in titles
    assert unknown_year.title not in titles
