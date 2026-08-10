"""library.refresh: chunked enrich+embed that never competes with an
in-flight paper analysis, and self-reschedules while backlog remains.
"""

import uuid

import pytest

from app.core.config import get_settings
from app.db.models import AnalysisRun, ReferencePaper
from app.db.models.enums import EnrichmentStatus, RunStatus
from app.workers.tasks.refresh_library import refresh_library
from tests.conftest import FIXTURES, upload_draft

pytestmark = pytest.mark.integration


async def _library_with_dataset(client):
    data = (FIXTURES / "sample_dataset.xlsx").read_bytes()
    await client.post("/api/v1/library/import", files={"file": ("sample_dataset.xlsx", data)})


async def test_refresh_defers_when_analysis_is_pending(client, db_session, monkeypatch):
    """An in-flight analysis (PENDING or RUNNING) must block library.refresh
    from doing any enrichment/embedding work at all, and must reschedule
    itself for later rather than silently dropping the tick.
    """
    await _library_with_dataset(client)
    draft_id = await upload_draft(client)

    db_session.add(
        AnalysisRun(id=uuid.uuid4(), draft_id=uuid.UUID(draft_id), status=RunStatus.PENDING)
    )
    db_session.commit()

    # Some fixture rows already carry a dataset-supplied abstract and import
    # as ENRICHED (see test_enrichment.py); the pending count, not "all
    # PENDING", is the baseline that must survive untouched.
    before = sorted(
        (r.id, r.enrichment_status) for r in db_session.query(ReferencePaper).all()
    )

    reschedule_calls = []
    monkeypatch.setattr(refresh_library, "apply_async", lambda **kw: reschedule_calls.append(kw))

    result = refresh_library(_reschedule=True)

    assert result == {"skipped": "analysis_in_flight"}
    assert len(reschedule_calls) == 1
    assert reschedule_calls[0]["countdown"] == get_settings().library_idle_retry_seconds

    # Nothing was touched.
    db_session.expire_all()
    after = sorted((r.id, r.enrichment_status) for r in db_session.query(ReferencePaper).all())
    assert after == before


async def test_refresh_processes_one_chunk_when_idle(client, db_session):
    """With no analysis running, a tick does real enrich+embed work."""
    await _library_with_dataset(client)

    result = refresh_library(_reschedule=False)

    assert result["enrich"] == {"enriched": 3, "incomplete": 2, "failed": 0}
    assert result["embed"]["embedded"] >= 1

    statuses = {r.enrichment_status for r in db_session.query(ReferencePaper).all()}
    assert EnrichmentStatus.ENRICHED in statuses


async def test_refresh_reschedules_when_a_full_chunk_was_processed(client, db_session, monkeypatch):
    """A chunk that came back full (>= chunk_size candidates processed)
    implies more backlog may remain, so the task must queue itself again.
    """
    await _library_with_dataset(client)

    settings = get_settings()
    monkeypatch.setattr(settings, "library_chunk_size", 2)  # smaller than the 5-row fixture

    reschedule_calls = []
    monkeypatch.setattr(refresh_library, "apply_async", lambda **kw: reschedule_calls.append(kw))

    result = refresh_library(_reschedule=True)

    assert (
        result["enrich"]["enriched"] + result["enrich"]["incomplete"] + result["enrich"]["failed"]
        == 2
    )
    assert len(reschedule_calls) == 1
    assert reschedule_calls[0]["countdown"] == 1


async def test_refresh_does_not_reschedule_when_backlog_is_exhausted(client, db_session, monkeypatch):
    await _library_with_dataset(client)

    reschedule_calls = []
    monkeypatch.setattr(refresh_library, "apply_async", lambda **kw: reschedule_calls.append(kw))

    # Default chunk size (25) comfortably covers the 5-row fixture, so the
    # whole backlog is processed in one chunk and nothing should remain.
    result = refresh_library(_reschedule=True)

    assert result["enrich"] == {"enriched": 3, "incomplete": 2, "failed": 0}
    assert reschedule_calls == []


async def test_refresh_skips_when_lock_already_held(client, db_session):
    """A concurrent invocation (overlapping Beat tick, or a manual trigger
    while one is already running) must not double-process the backlog.
    """
    import redis

    await _library_with_dataset(client)
    before = sorted(
        (r.id, r.enrichment_status) for r in db_session.query(ReferencePaper).all()
    )

    client_redis = redis.Redis.from_url(get_settings().redis_url)
    assert client_redis.set("library_refresh_lock", "1", nx=True, ex=60)
    try:
        result = refresh_library(_reschedule=False)
        assert result == {"skipped": "already_running"}
        db_session.expire_all()
        after = sorted((r.id, r.enrichment_status) for r in db_session.query(ReferencePaper).all())
        assert after == before
    finally:
        client_redis.delete("library_refresh_lock")
