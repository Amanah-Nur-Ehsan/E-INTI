from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from sqlalchemy import case, func, select

from app.api.deps import SessionDep
from app.core.uploads import read_upload_capped
from app.db.models import ReferencePaper
from app.schemas.analysis import ReferenceCounts
from app.schemas.reference import ImportResult, MissingAbstractsByYear, ReferenceRead
from app.services.dataset_import_service import DatasetSchemaError, import_dataset
from app.services.progress import reference_counts

router = APIRouter(prefix="/library", tags=["library"])


@router.post("/import", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
async def import_references(session: SessionDep, file: UploadFile = File(...)) -> ImportResult:
    content = await read_upload_capped(file)

    # The importer is sync (shared with worker code); run it on the sync engine.
    from app.db.session import get_sync_session_factory

    try:
        with get_sync_session_factory()() as sync_session:
            summary = import_dataset(sync_session, content, file.filename or "upload.xlsx")
    except DatasetSchemaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    return ImportResult(**summary.__dict__)


@router.post("/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_library() -> dict:
    """Kick off enrichment-then-embedding for every pending library row.

    Not tied to an AnalysisRun -- the library is maintained on its own
    schedule, separate from any particular draft's analysis.
    """
    from app.workers.tasks.refresh_library import refresh_library as refresh_task

    async_result = refresh_task.delay()
    return {"task_id": async_result.id}


@router.get("/status", response_model=ReferenceCounts)
async def references_status(session: SessionDep) -> ReferenceCounts:
    return await reference_counts(session)


@router.get("/missing-abstracts-by-year", response_model=list[MissingAbstractsByYear])
async def missing_abstracts_by_year(session: SessionDep) -> list[MissingAbstractsByYear]:
    """Where to focus manual abstract collection: which publication years
    have the most references still missing an abstract, so a user filling
    them in by hand (or re-exporting from Scopus) knows where to start.
    """
    missing_expr = func.sum(case((ReferencePaper.abstract.is_(None), 1), else_=0))
    stmt = (
        select(
            ReferencePaper.year,
            missing_expr.label("missing"),
            func.count().label("total"),
        )
        .group_by(ReferencePaper.year)
        .having(missing_expr > 0)
        .order_by(missing_expr.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        MissingAbstractsByYear(year=year, missing=missing, total=total)
        for year, missing, total in rows
    ]


@router.get("", response_model=list[ReferenceRead])
async def list_references(
    session: SessionDep,
    enrichment_status: str | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[ReferencePaper]:
    stmt = select(ReferencePaper)
    if enrichment_status:
        stmt = stmt.where(ReferencePaper.enrichment_status == enrichment_status)
    stmt = stmt.order_by(ReferencePaper.original_row_number).limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars())
