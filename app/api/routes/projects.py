import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import ProjectDep, SessionDep
from app.db.models import Project
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, session: SessionDep) -> Project:
    project = Project(**payload.model_dump())
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
async def list_projects(session: SessionDep) -> list[Project]:
    result = await session.execute(select(Project).order_by(Project.created_at.desc()))
    return list(result.scalars())


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project: ProjectDep) -> Project:
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(project: ProjectDep, payload: ProjectUpdate, session: SessionDep) -> Project:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await session.commit()
    await session.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: uuid.UUID, project: ProjectDep, session: SessionDep) -> None:
    await session.delete(project)
    await session.commit()
