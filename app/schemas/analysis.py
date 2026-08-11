import uuid
from datetime import datetime

from pydantic import BaseModel


class ReferenceCounts(BaseModel):
    total: int
    pending: int
    enriched: int
    incomplete: int
    failed: int
    embedded: int
    #: abstract IS NULL -- structurally unreachable by retrieval no matter
    #: how much enrichment/embedding runs, until an abstract is filled in.
    missing_abstract: int
    #: abstract IS NOT NULL AND content_hash IS NULL -- has what it needs to
    #: be embedded but the vector hasn't been (re)computed yet. This is the
    #: number that would have caught the embedding livelock: `embedded`
    #: alone looked fine sitting at 115 with nothing to compare it against.
    embed_pending: int


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
    #: Set once the CLASSIFYING_SDG stage completes; null before then.
    sdg_number: int | None = None
    sdg_name: str | None = None
    sdg_keyword: str | None = None
    sdg_rationale: str | None = None
    #: Set only when the classifier declined (sdg_number is null): the
    #: best-ranked candidate it considered but judged not a genuine fit.
    sdg_closest_number: int | None = None
    sdg_closest_name: str | None = None


class AnalysisRunAccepted(BaseModel):
    run_id: uuid.UUID
    draft_id: uuid.UUID
    status: str


class DraftSummary(BaseModel):
    """Dashboard summary. `coverage_percentage` is computed once here so the
    dashboard and any other consumer (export, future reporting) can never
    disagree about what "coverage" means.
    """

    draft_id: uuid.UUID
    references: ReferenceCounts
    claims: ClaimCounts
    accepted_citations: int
    claims_with_accepted: int
    coverage_percentage: float
    latest_run: AnalysisRunStatus | None
