import uuid

from celery import chain
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import DraftDep, SessionDep
from app.db.models import AnalysisRun, Draft, ReferencePaper
from app.db.models.enums import RunStatus
from app.schemas.analysis import AnalysisRunAccepted, AnalysisRunStatus, DraftSummary
from app.services.progress import accepted_citation_counts, claim_counts, reference_counts

router = APIRouter(prefix="/drafts/{draft_id}", tags=["analysis"])


def build_analysis_chain(run_id: uuid.UUID):
    """Linear chain of idempotent stages; each stage takes only the run id.

    Enrichment and embedding are no longer part of a per-draft run -- the
    reference library is maintained on its own schedule via
    POST /library/refresh, since that cost belongs to the paper, not to
    whichever draft happens to cite it.
    """
    from app.workers.tasks.classify_sdg import classify_sdg
    from app.workers.tasks.detect_claims import detect_claims
    from app.workers.tasks.generate_recommendations import generate_recommendations
    from app.workers.tasks.parse_draft import parse_draft

    rid = str(run_id)
    return chain(
        parse_draft.si(rid),
        classify_sdg.si(rid),
        detect_claims.si(rid),
        generate_recommendations.si(rid),
    )


@router.post(
    "/analysis/run", response_model=AnalysisRunAccepted, status_code=status.HTTP_202_ACCEPTED
)
async def run_analysis(draft: DraftDep, session: SessionDep) -> AnalysisRunAccepted:
    n_refs = (
        await session.execute(select(func.count()).select_from(ReferencePaper))
    ).scalar_one()
    if n_refs == 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "The reference library is empty -- import the dataset first"
        )

    active = (
        (
            await session.execute(
                select(AnalysisRun).where(
                    AnalysisRun.draft_id == draft.id,
                    AnalysisRun.status.in_([RunStatus.PENDING, RunStatus.RUNNING]),
                )
            )
        )
        .scalars()
        .first()
    )
    if active is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Analysis run {active.id} is already in progress"
        )

    run = AnalysisRun(draft_id=draft.id, status=RunStatus.PENDING)
    session.add(run)
    await session.commit()
    await session.refresh(run)

    async_result = build_analysis_chain(run.id).apply_async()
    run.celery_root_id = str(async_result.id)
    await session.commit()
    await session.refresh(run)

    return AnalysisRunAccepted(run_id=run.id, draft_id=draft.id, status=run.status)


async def _latest_run(session, draft_id: uuid.UUID) -> AnalysisRun | None:
    return (
        (
            await session.execute(
                select(AnalysisRun)
                .where(AnalysisRun.draft_id == draft_id)
                .order_by(AnalysisRun.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def _build_run_status(session, run: AnalysisRun) -> AnalysisRunStatus:
    # The worker writes through a different connection; expire to read fresh state.
    await session.refresh(run)
    draft = await session.get(Draft, run.draft_id)
    return AnalysisRunStatus(
        run_id=run.id,
        draft_id=run.draft_id,
        status=run.status,
        stage=run.stage,
        error=run.error,
        started_at=run.started_at,
        finished_at=run.finished_at,
        references=await reference_counts(session),
        claims=await claim_counts(session, run.draft_id),
        sdg_number=draft.sdg_number if draft else None,
        sdg_name=draft.sdg_name if draft else None,
        sdg_keyword=draft.sdg_keyword if draft else None,
        sdg_rationale=draft.sdg_rationale if draft else None,
        sdg_closest_number=draft.sdg_closest_number if draft else None,
        sdg_closest_name=draft.sdg_closest_name if draft else None,
    )


@router.get("/analysis/status", response_model=AnalysisRunStatus)
async def analysis_status(draft: DraftDep, session: SessionDep) -> AnalysisRunStatus:
    run = await _latest_run(session, draft.id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No analysis run for this draft")
    return await _build_run_status(session, run)


@router.get("/summary", response_model=DraftSummary)
async def draft_summary(draft: DraftDep, session: SessionDep) -> DraftSummary:
    """Dashboard data in one call: reference/claim counts, acceptance
    coverage, and the latest analysis run's status (if any has run yet).
    """
    run = await _latest_run(session, draft.id)

    references = await reference_counts(session)
    claims = await claim_counts(session, draft.id)
    accepted_total, claims_with_accepted = await accepted_citation_counts(session, draft.id)

    coverage = (
        round(100 * claims_with_accepted / claims.needs_citation, 1)
        if claims.needs_citation > 0
        else 0.0
    )

    return DraftSummary(
        draft_id=draft.id,
        references=references,
        claims=claims,
        accepted_citations=accepted_total,
        claims_with_accepted=claims_with_accepted,
        coverage_percentage=coverage,
        latest_run=await _build_run_status(session, run) if run else None,
    )
