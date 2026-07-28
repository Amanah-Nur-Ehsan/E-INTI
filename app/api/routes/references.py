from fastapi import APIRouter

from app.api.deps import ProjectDep, SessionDep
from app.schemas.analysis import ReferenceCounts
from app.services.progress import reference_counts

router = APIRouter(prefix="/projects/{project_id}/references", tags=["references"])


@router.get("/status", response_model=ReferenceCounts)
async def references_status(project: ProjectDep, session: SessionDep) -> ReferenceCounts:
    return await reference_counts(session, project.id)
