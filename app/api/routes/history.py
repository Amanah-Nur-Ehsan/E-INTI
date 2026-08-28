import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.db.models import AnalysisRun, Draft
from app.schemas.history import AnalysisHistoryItem

router = APIRouter(prefix="/analysis/history", tags=["analysis"])


@router.get("", response_model=list[AnalysisHistoryItem])
async def list_history(session: SessionDep) -> list[AnalysisHistoryItem]:
    """All past analyses, newest first, with a summary drawn from each run's
    stored result snapshot."""
    rows = (
        await session.execute(
            select(AnalysisRun, Draft)
            .join(Draft, AnalysisRun.draft_id == Draft.id)
            .order_by(AnalysisRun.created_at.desc())
        )
    ).all()

    items: list[AnalysisHistoryItem] = []
    for run, draft in rows:
        result = run.result_json or {}
        summary = result.get("summary") or {}
        sdg = result.get("sdg") or {}
        items.append(
            AnalysisHistoryItem(
                run_id=run.id,
                draft_id=run.draft_id,
                filename=draft.original_filename,
                status=run.status,
                error=run.error,
                finished_at=run.finished_at,
                created_at=run.created_at,
                sdg_number=sdg.get("number"),
                sdg_name=sdg.get("name"),
                claims_total=summary.get("claims_total"),
                recommendations=summary.get("recommendations"),
                accepted=summary.get("accepted"),
            )
        )
    return items


@router.get("/{run_id}")
async def get_history_detail(run_id: uuid.UUID, session: SessionDep) -> dict:
    """The frozen result snapshot of one completed analysis."""
    run = await session.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis run not found")
    if not run.result_json:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No stored result for this run"
        )
    return run.result_json
