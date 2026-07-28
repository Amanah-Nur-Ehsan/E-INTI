import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    description: str | None = None
    field_of_study: str | None = None
    citation_style: str = "APA"


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    field_of_study: str | None = None
    citation_style: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    field_of_study: str | None
    citation_style: str
    created_at: datetime
    updated_at: datetime
