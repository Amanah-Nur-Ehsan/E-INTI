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


class ReferenceDetail(ReferenceSummary):
    """The fuller "view details of the chosen paper" picture -- everything
    ReferenceSummary has, plus the fields only worth showing once a paper
    has actually been singled out as the one to cite.
    """

    source_link: str | None
    citation_count: int | None
    document_type: str | None
    field_of_study: str | None
    author_keywords: list[str] | None
    index_keywords: list[str] | None
    subject_areas: list[str] | None
    publisher_url: str | None


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


class BestReferenceClaim(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section_title: str | None
    sentence_text: str
    local_context: str


class BestReferenceRead(BaseModel):
    """The single reference this paper should cite -- one pick across the
    whole draft, not one per claim. `meets_threshold`/`is_recommended` let
    the UI show *something* even on a weak match rather than a blank page,
    while still being honest that it's weak.
    """

    recommendation: RecommendationRead
    claim: BestReferenceClaim
    reference: ReferenceDetail
    meets_threshold: bool
    is_recommended: bool
    min_score_threshold: float
    recommended_score_threshold: float


class ParagraphRewriteRequest(BaseModel):
    #: One of citation_formatting_service.SUPPORTED_STYLES.
    style: str = "APA"


class ParagraphRewriteRead(BaseModel):
    paragraph: str
    in_text_citation: str
    bibliography_entry: str
    style: str


class DecisionRequest(BaseModel):
    note: str | None = None


class SetDecisionRequest(BaseModel):
    """Body for the unified /decision endpoint, which accepts any of the
    three UserDecision outcomes the review UI can produce. accept/reject
    remain as thin aliases hard-coding `decision` for backward compatibility.
    """

    decision: str  # one of UserDecision: ACCEPTED | REJECTED | IRRELEVANT
    note: str | None = None
