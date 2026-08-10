"""Standalone library maintenance task: enrich-then-embed the pending
backlog in small chunks, never competing with an in-flight paper analysis
for the worker's two thread slots.

Not part of the per-draft AnalysisRun chain -- the library is a shared
resource maintained on its own schedule (POST /library/refresh, or the
idle-time Celery Beat tick registered in celery_app.py), since
enrichment/embedding cost belongs to the paper, not to whichever draft
happens to cite it.

Priority is enforced by refusing to *start* work, not by preempting work
already running -- Celery/Redis have no preemption primitive, and with
only two thread slots a long-running chunk would still starve an incoming
analysis for its duration. So each invocation processes at most
`settings.library_chunk_size` rows, checks for an in-flight AnalysisRun
before that chunk (not just once at the top, since this task
self-reschedules and re-checks every time), and immediately backs off
without doing any work if one is found -- "just the needed one" applies to
background maintenance exactly as much as to LLM calls.
"""

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import AnalysisRun
from app.db.models.enums import RunStatus
from app.db.session import get_sync_session_factory
from app.workers.celery_app import celery_app

log = get_logger(__name__)

_LOCK_KEY = "library_refresh_lock"
#: Generous relative to one chunk's expected runtime (a few seconds to
#: tens of seconds for 25 rows) -- this is a "don't double-run" guard
#: against overlapping Beat ticks / manual triggers, not a tight budget.
_LOCK_TTL_SECONDS = 300


def _redis_client():
    import redis

    return redis.Redis.from_url(get_settings().redis_url)


def _any_analysis_in_flight(session) -> bool:
    return (
        session.execute(
            select(AnalysisRun.id)
            .where(AnalysisRun.status.in_([RunStatus.PENDING, RunStatus.RUNNING]))
            .limit(1)
        ).first()
        is not None
    )


@celery_app.task(name="library.refresh")
def refresh_library(_reschedule: bool = True) -> dict:
    """Process one chunk of the pending backlog, or no-op and reschedule.

    `_reschedule=False` is for tests and any caller that wants exactly one
    chunk's worth of work with no follow-up Celery call queued.
    """
    settings = get_settings()
    client = _redis_client()
    if not client.set(_LOCK_KEY, "1", nx=True, ex=_LOCK_TTL_SECONDS):
        log.info("library_refresh_skipped_already_running")
        return {"skipped": "already_running"}

    try:
        with get_sync_session_factory()() as session:
            if _any_analysis_in_flight(session):
                log.info("library_refresh_deferred_analysis_in_flight")
                if _reschedule:
                    refresh_library.apply_async(
                        countdown=settings.library_idle_retry_seconds
                    )
                return {"skipped": "analysis_in_flight"}

            from app.services.embedding_service import embed_pending_references
            from app.services.enrichment import enrich_pending_references

            chunk = settings.library_chunk_size
            enrich_counts = enrich_pending_references(session, limit=chunk)
            embed_counts = embed_pending_references(session, limit=chunk)
    finally:
        client.delete(_LOCK_KEY)

    log.info("library_refresh_chunk_done", enrich=enrich_counts, embed=embed_counts)

    # Neither counts dict reports "how many PENDING rows are left" directly
    # -- but each candidate query was capped at `chunk`, so processing a
    # full chunk's worth of candidates (rather than fewer) means the
    # backlog likely isn't exhausted yet. Cheaper than a second COUNT
    # query, and wrong only in the direction of one harmless extra chunk.
    enrich_processed = sum(enrich_counts.get(k, 0) for k in ("enriched", "incomplete", "failed"))
    embed_processed = embed_counts.get("embedded", 0) + embed_counts.get("skipped", 0)
    work_remaining = enrich_processed >= chunk or embed_processed >= chunk

    if _reschedule and work_remaining:
        refresh_library.apply_async(countdown=1)

    return {"enrich": enrich_counts, "embed": embed_counts}
