from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select

from app.api.deps import ProjectDep, SessionDep
from app.db.models import ReferencePaper
from app.schemas.analysis import ReferenceCounts
from app.schemas.reference import ImportResult, ReferenceRead
from app.services.dataset_import_service import DatasetSchemaError, import_dataset
from app.services.progress import reference_counts

router = APIRouter(prefix="/projects/{project_id}/references", tags=["references"])


@router.post("/import", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
async def import_references(
    project: ProjectDep, session: SessionDep, file: UploadFile = File(...)
) -> ImportResult:
    content = await file.read()

    # The importer is sync (shared with worker code); run it on the sync engine.
    from app.db.session import get_sync_session_factory

    try:
        with get_sync_session_factory()() as sync_session:
            summary = import_dataset(sync_session, project.id, content, file.filename or "upload.xlsx")
    except DatasetSchemaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    return ImportResult(**summary.__dict__)


@router.get("/status", response_model=ReferenceCounts)
async def references_status(project: ProjectDep, session: SessionDep) -> ReferenceCounts:
    return await reference_counts(session, project.id)


@router.get("", response_model=list[ReferenceRead])
async def list_references(
    project: ProjectDep,
    session: SessionDep,
    enrichment_status: str | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[ReferencePaper]:
    stmt = select(ReferencePaper).where(ReferencePaper.project_id == project.id)
    if enrichment_status:
        stmt = stmt.where(ReferencePaper.enrichment_status == enrichment_status)
    stmt = stmt.order_by(ReferencePaper.original_row_number).limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars())
