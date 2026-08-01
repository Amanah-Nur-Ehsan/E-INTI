"""Standalone library maintenance task: enrich-then-embed every pending row.

Not part of the per-draft AnalysisRun chain -- the library is a shared
resource maintained on its own schedule (POST /library/refresh), since
enrichment/embedding cost belongs to the paper, not to whichever draft
happens to cite it.
"""

from app.core.logging import get_logger
from app.db.session import get_sync_session_factory
from app.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="library.refresh")
def refresh_library() -> dict:
    from app.services.embedding_service import embed_pending_references
    from app.services.enrichment import enrich_pending_references

    with get_sync_session_factory()() as session:
        enrich_counts = enrich_pending_references(session)
        embed_counts = embed_pending_references(session)

    log.info("library_refresh_done", enrich=enrich_counts, embed=embed_counts)
    return {"enrich": enrich_counts, "embed": embed_counts}
