"""library.refresh: chunked enrich+embed that never competes with an
in-flight paper analysis, and self-reschedules while backlog remains.
"""

import uuid

import pytest

from app.core.config import get_settings
from app.db.models import AnalysisRun, ReferencePaper
from app.db.models.enums import EnrichmentProvider, EnrichmentStatus, RunStatus
from app.services.embedding_service import embed_pending_references
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


async def test_embed_chunking_does_not_livelock_on_already_embedded_rows(db_session, monkeypatch):
    """Regression test for the actual bug: a previous version of
    embed_pending_references filtered only `abstract IS NOT NULL` and
    decided "already current, skip" in Python *after* LIMIT was applied.
    With a chunk size smaller than the embedded backlog, that meant the
    same oldest N already-embedded rows were re-selected and skipped on
    every tick forever -- refresh_library counted those skips as progress
    and kept rescheduling itself, never reaching the genuinely-pending rows
    behind them.

    Seeds more rows than one chunk, embeds all of them up front (so
    they're all "already current" -- the exact condition that triggered
    the livelock), adds a handful of genuinely new rows behind them, and
    asserts a small-chunked refresh_library run actually reaches and
    embeds the new ones instead of spinning on the old ones.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "library_chunk_size", 3)

    for i in range(6):
        db_session.add(
            ReferencePaper(
                title=f"Already embedded paper {i}",
                abstract=f"Abstract for already embedded paper {i}.",
                enrichment_status=EnrichmentStatus.ENRICHED,
                enrichment_provider=EnrichmentProvider.DATASET,
            )
        )
    db_session.commit()
    # All 6 become current -- this is the state that livelocked before.
    assert embed_pending_references(db_session)["embedded"] == 6

    new_rows = [
        ReferencePaper(
            title=f"New paper {i}",
            abstract=f"Abstract for new paper {i}.",
            enrichment_status=EnrichmentStatus.ENRICHED,
            enrichment_provider=EnrichmentProvider.DATASET,
        )
        for i in range(4)
    ]
    db_session.add_all(new_rows)
    db_session.commit()

    reschedule_calls = []
    monkeypatch.setattr(refresh_library, "apply_async", lambda **kw: reschedule_calls.append(kw))

    # Drive the self-reschedule loop manually (apply_async is mocked, so it
    # doesn't actually re-enqueue) until it stops asking to be rescheduled,
    # with a hard cap so a real livelock fails the test instead of hanging.
    for _ in range(20):
        if not reschedule_calls:
            refresh_library(_reschedule=True)
        else:
            reschedule_calls.pop()
            refresh_library(_reschedule=True)
        if not reschedule_calls:
            break
    else:
        pytest.fail("refresh_library kept rescheduling itself -- livelock reproduced")

    db_session.expire_all()
    new_ids = {r.id for r in new_rows}
    embedded_new = (
        db_session.query(ReferencePaper)
        .filter(ReferencePaper.id.in_(new_ids), ReferencePaper.embedding.isnot(None))
        .count()
    )
    assert embedded_new == 4


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
