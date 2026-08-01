import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import ExportFormat, InsertionMode


class ExportRequest(BaseModel):
    format: ExportFormat
    citation_style: str = "APA"
    insertion_mode: InsertionMode = InsertionMode.TRACKED_CHANGES
    include_audit_report: bool = True


class ExportOutcome(BaseModel):
    claim_id: uuid.UUID
    status: str
    citation_text: str | None = None
    paragraph_index: int | None = None


class ExportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    draft_id: uuid.UUID
    format: str
    citation_style: str
    insertion_mode: str
    include_audit_report: bool
    filename: str
    byte_size: int
    inserted_count: int
    mismatch_count: int
    outcomes: list[ExportOutcome] = Field(default_factory=list)
    created_at: datetime
