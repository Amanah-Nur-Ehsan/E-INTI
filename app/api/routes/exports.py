import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import ProjectDep, SessionDep
from app.db.models import Export
from app.schemas.export import ExportRead, ExportRequest
from app.services.export import UnsupportedExportError, run_export
from app.services.export.bundle import DraftNotParsedError

router = APIRouter(tags=["exports"])

_CONTENT_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "md": "text/markdown",
    "csv": "text/csv",
    "json": "application/json",
}


@router.post(
    "/projects/{project_id}/exports", response_model=ExportRead, status_code=status.HTTP_201_CREATED
)
async def create_export(project: ProjectDep, payload: ExportRequest, session: SessionDep) -> Export:
    # The generator (python-docx et al.) is sync and blocking; run it in the
    # threadpool FastAPI already provides for sync dependencies/routes rather
    # than blocking the event loop. The DB write also uses the sync engine,
    # matching the pattern used by dataset import and analysis tasks.
    from app.db.session import get_sync_session_factory

    def _run() -> Export:
        with get_sync_session_factory()() as sync_session:
            return run_export(
                sync_session,
                project.id,
                format=payload.format,
                draft_id=payload.draft_id,
                citation_style=payload.citation_style,
                insertion_mode=payload.insertion_mode,
                include_audit_report=payload.include_audit_report,
            )

    try:
        import anyio

        return await anyio.to_thread.run_sync(_run)
    except DraftNotParsedError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except UnsupportedExportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except ValueError as exc:
        # DOCX export requested for a non-.docx draft, or no draft uploaded.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/projects/{project_id}/exports", response_model=list[ExportRead])
async def list_exports(project: ProjectDep, session: SessionDep) -> list[Export]:
    result = await session.execute(
        select(Export).where(Export.project_id == project.id).order_by(Export.created_at.desc())
    )
    return list(result.scalars())


@router.get("/exports/{export_id}/download")
async def download_export(export_id: uuid.UUID, session: SessionDep) -> FileResponse:
    export = await session.get(Export, export_id)
    if export is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Export {export_id} not found")

    return FileResponse(
        export.storage_path,
        media_type=_CONTENT_TYPES.get(export.format, "application/octet-stream"),
        filename=export.filename,
    )
