import uuid
from datetime import datetime

from pydantic import BaseModel


class AnalysisRunRequest(BaseModel):
    #: Defaults to the project's most recently uploaded draft.
    draft_id: uuid.UUID | None = None


class ReferenceCounts(BaseModel):
    total: int
    pending: int
    enriched: int
    incomplete: int
    failed: int
    embedded: int


class ClaimCounts(BaseModel):
    total: int
    needs_citation: int
    with_recommendations: int


class AnalysisRunStatus(BaseModel):
    run_id: uuid.UUID
    draft_id: uuid.UUID
    status: str
    stage: str | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    references: ReferenceCounts
    claims: ClaimCounts


class AnalysisRunAccepted(BaseModel):
    run_id: uuid.UUID
    draft_id: uuid.UUID
    status: str


class ProjectSummary(BaseModel):
    """Dashboard summary. `coverage_percentage` is computed once here so the
    dashboard and any other consumer (export, future reporting) can never
    disagree about what "coverage" means.
    """

    project_id: uuid.UUID
    draft_id: uuid.UUID | None
    references: ReferenceCounts
    claims: ClaimCounts
    accepted_citations: int
    claims_with_accepted: int
    coverage_percentage: float
    latest_run: AnalysisRunStatus | None
