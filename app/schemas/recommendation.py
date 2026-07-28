import uuid

from pydantic import BaseModel, ConfigDict


class ScoreBreakdownOut(BaseModel):
    semantic_similarity: float | None
    lexical_similarity: float | None
    keyword_overlap: float | None
    field_match: float | None
    reranker_score: float | None
    llm_support_score: float | None


class ReferenceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    authors: list | None
    year: int | None
    source_title: str | None
    doi: str | None
    scopus_url: str | None
    abstract: str | None


class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_id: uuid.UUID
    reference_id: uuid.UUID
    rank: int
    score_percentage: float
    final_score: float
    recommendation_label: str | None
    verdict: str
    recommended_usage: str | None
    evidence_paraphrase: str | None
    limitations: str | None
    user_decision: str
    user_note: str | None
    score_breakdown: ScoreBreakdownOut
    reference: ReferenceSummary


class DecisionRequest(BaseModel):
    note: str | None = None


class SetDecisionRequest(BaseModel):
    """Body for the unified /decision endpoint, which accepts any of the
    three UserDecision outcomes the review UI can produce. accept/reject
    remain as thin aliases hard-coding `decision` for backward compatibility.
    """

    decision: str  # one of UserDecision: ACCEPTED | REJECTED | IRRELEVANT
    note: str | None = None
