import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import DraftDep, ProjectDep, SessionDep
from app.core.config import get_settings
from app.core.uploads import save_upload_capped
from app.db.models import Draft
from app.schemas.draft import DraftDetail, DraftRead

router = APIRouter(tags=["drafts"])

SUPPORTED_SUFFIXES = {".docx", ".md", ".markdown", ".txt"}
MIME_BY_SUFFIX = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
}


@router.post(
    "/projects/{project_id}/drafts/upload",
    response_model=DraftRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_draft(
    project: ProjectDep, session: SessionDep, file: UploadFile = File(...)
) -> Draft:
    filename = file.filename or "draft.docx"
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Unsupported draft format '{suffix}'. Supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}",
        )

    draft_id = uuid.uuid4()
    directory = get_settings().upload_dir / str(project.id) / "drafts"
    directory.mkdir(parents=True, exist_ok=True)
    storage_path = directory / f"{draft_id}{suffix}"
    await save_upload_capped(file, storage_path)

    draft = Draft(
        id=draft_id,
        project_id=project.id,
        original_filename=filename,
        storage_path=str(storage_path),
        mime_type=file.content_type or MIME_BY_SUFFIX[suffix],
    )
    session.add(draft)
    await session.commit()
    await session.refresh(draft)
    return draft


@router.get("/projects/{project_id}/drafts", response_model=list[DraftRead])
async def list_drafts(project: ProjectDep, session: SessionDep) -> list[Draft]:
    result = await session.execute(
        select(Draft).where(Draft.project_id == project.id).order_by(Draft.created_at.desc())
    )
    return list(result.scalars())


@router.get("/drafts/{draft_id}", response_model=DraftDetail)
async def get_draft(draft: DraftDep) -> Draft:
    return draft
