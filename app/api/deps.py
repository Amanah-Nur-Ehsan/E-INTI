import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Draft, Project
from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_project_or_404(project_id: uuid.UUID, session: SessionDep) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project {project_id} not found")
    return project


async def get_draft_or_404(draft_id: uuid.UUID, session: SessionDep) -> Draft:
    draft = await session.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Draft {draft_id} not found")
    return draft


ProjectDep = Annotated[Project, Depends(get_project_or_404)]
DraftDep = Annotated[Draft, Depends(get_draft_or_404)]
