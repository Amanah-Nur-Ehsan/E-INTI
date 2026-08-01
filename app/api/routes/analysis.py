import uuid

from celery import chain
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import ProjectDep, SessionDep
from app.db.models import AnalysisRun, Draft, ReferencePaper
from app.db.models.enums import RunStatus
from app.schemas.analysis import (
    AnalysisRunAccepted,
    AnalysisRunRequest,
    AnalysisRunStatus,
    ClaimCounts,
    ProjectSummary,
)
from app.services.progress import (
    accepted_citation_counts,
    claim_counts,
    latest_draft_id,
    reference_counts,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["analysis"])


def build_analysis_chain(run_id: uuid.UUID):
    """Linear chain of idempotent stages; each stage takes only the run id.

    Enrichment and embedding are no longer part of a per-draft run -- the
    reference library is maintained on its own schedule via
    POST /library/refresh, since that cost belongs to the paper, not to
    whichever draft happens to cite it.
    """
    from app.workers.tasks.detect_claims import detect_claims
    from app.workers.tasks.generate_recommendations import generate_recommendations
    from app.workers.tasks.parse_draft import parse_draft

    rid = str(run_id)
    return chain(
        parse_draft.si(rid),
        detect_claims.si(rid),
        generate_recommendations.si(rid),
    )


@router.post(
    "/analysis/run", response_model=AnalysisRunAccepted, status_code=status.HTTP_202_ACCEPTED
)
async def run_analysis(
    project: ProjectDep, payload: AnalysisRunRequest, session: SessionDep
) -> AnalysisRunAccepted:
    draft_id = payload.draft_id or await latest_draft_id(session, project.id)
    if draft_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Project has no uploaded draft")

    draft = await session.get(Draft, draft_id)
    if draft is None or draft.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Draft {draft_id} not found in project")

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
                    AnalysisRun.project_id == project.id,
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

    run = AnalysisRun(project_id=project.id, draft_id=draft_id, status=RunStatus.PENDING)
    session.add(run)
    await session.commit()
    await session.refresh(run)

    async_result = build_analysis_chain(run.id).apply_async()
    run.celery_root_id = str(async_result.id)
    await session.commit()
    await session.refresh(run)

    return AnalysisRunAccepted(run_id=run.id, draft_id=draft_id, status=run.status)


async def _latest_run(session, project_id: uuid.UUID) -> AnalysisRun | None:
    return (
        (
            await session.execute(
                select(AnalysisRun)
                .where(AnalysisRun.project_id == project_id)
                .order_by(AnalysisRun.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def _build_run_status(session, project_id: uuid.UUID, run: AnalysisRun) -> AnalysisRunStatus:
    # The worker writes through a different connection; expire to read fresh state.
    await session.refresh(run)
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
    )


@router.get("/analysis/status", response_model=AnalysisRunStatus)
async def analysis_status(project: ProjectDep, session: SessionDep) -> AnalysisRunStatus:
    run = await _latest_run(session, project.id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No analysis run for this project")
    return await _build_run_status(session, project.id, run)


@router.get("/summary", response_model=ProjectSummary)
async def project_summary(project: ProjectDep, session: SessionDep) -> ProjectSummary:
    """Dashboard data in one call: reference/claim counts, acceptance
    coverage, and the latest analysis run's status (if any has run yet).
    """
    draft_id = await latest_draft_id(session, project.id)
    run = await _latest_run(session, project.id)

    references = await reference_counts(session)
    if draft_id is not None:
        claims = await claim_counts(session, draft_id)
        accepted_total, claims_with_accepted = await accepted_citation_counts(session, draft_id)
    else:
        claims = ClaimCounts(total=0, needs_citation=0, with_recommendations=0)
        accepted_total, claims_with_accepted = 0, 0

    coverage = (
        round(100 * claims_with_accepted / claims.needs_citation, 1)
        if claims.needs_citation > 0
        else 0.0
    )

    return ProjectSummary(
        project_id=project.id,
        draft_id=draft_id,
        references=references,
        claims=claims,
        accepted_citations=accepted_total,
        claims_with_accepted=claims_with_accepted,
        coverage_percentage=coverage,
        latest_run=await _build_run_status(session, project.id, run) if run else None,
    )
