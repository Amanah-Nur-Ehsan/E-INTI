import uuid
from datetime import datetime

from pydantic import BaseModel


class AnalysisHistoryItem(BaseModel):
    run_id: uuid.UUID
    draft_id: uuid.UUID
    filename: str
    status: str
    error: str | None
    finished_at: datetime | None
    created_at: datetime
    sdg_number: int | None
    sdg_name: str | None
    claims_total: int | None
    recommendations: int | None
    accepted: int | None
