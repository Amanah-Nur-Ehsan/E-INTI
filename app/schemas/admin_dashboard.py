from datetime import datetime

from pydantic import BaseModel

from app.schemas.analysis import ReferenceCounts


class UserCounts(BaseModel):
    total: int
    active: int
    admins: int


class AppStatus(BaseModel):
    environment: str
    active_analyses: int
    last_run_status: str | None
    last_run_stage: str | None
    last_run_started_at: datetime | None
    last_run_finished_at: datetime | None
    last_run_error: str | None


class AdminOverview(BaseModel):
    users: UserCounts
    library: ReferenceCounts
    app: AppStatus
