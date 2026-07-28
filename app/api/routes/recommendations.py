import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import SessionDep
from app.db.models import AcceptedCitation, CitationRecommendation, Claim, ReferencePaper
from app.db.models.enums import UserDecision
from app.schemas.recommendation import (
    DecisionRequest,
    RecommendationRead,
    ReferenceSummary,
    ScoreBreakdownOut,
)
from app.services.citation_formatting_service import build_citation_context

router = APIRouter(tags=["recommendations"])


async def _recompute_accepted_citation_texts(session, draft_id: uuid.UUID) -> None:
    """Re-derive `citation_text` for every accepted citation in a draft.

    Year-letter disambiguation ("2024a" vs "2024b") depends on the whole
    accepted set, not on any one reference in isolation, so accepting or
    rejecting a citation can change what an *already*-accepted sibling
    should display. Recomputing the whole set keeps ghost text consistent
    with what export will eventually write, at the cost of one extra query
    per accept/reject -- cheap at review-screen scale.
    """
    rows = (
        await session.execute(
            select(AcceptedCitation, ReferencePaper)
            .join(ReferencePaper, ReferencePaper.id == AcceptedCitation.reference_id)
            .join(Claim, Claim.id == AcceptedCitation.claim_id)
            .where(Claim.draft_id == draft_id)
        )
    ).all()
    if not rows:
        return

    references = {ref.id: ref for _accepted, ref in rows}
    context = build_citation_context(list(references.values()))
    for accepted, ref in rows:
        accepted.citation_text = context.in_text(ref.id)
        accepted.insertion_format = "APA"


def _serialize(
    recommendation: CitationRecommendation, reference: ReferencePaper
) -> RecommendationRead:
    return RecommendationRead(
        id=recommendation.id,
        claim_id=recommendation.claim_id,
        reference_id=recommendation.reference_id,
        rank=recommendation.rank,
        score_percentage=recommendation.score_percentage,
        final_score=recommendation.final_score,
        recommendation_label=recommendation.recommendation_label,
        verdict=recommendation.verdict,
        recommended_usage=recommendation.recommended_usage,
        evidence_paraphrase=recommendation.evidence_paraphrase,
        limitations=recommendation.limitations,
        user_decision=recommendation.user_decision,
        user_note=recommendation.user_note,
        score_breakdown=ScoreBreakdownOut(
            semantic_similarity=recommendation.semantic_similarity,
            lexical_similarity=recommendation.lexical_similarity,
            keyword_overlap=recommendation.keyword_overlap,
            field_match=recommendation.field_match,
            reranker_score=recommendation.reranker_score,
            llm_support_score=recommendation.llm_support_score,
        ),
        reference=ReferenceSummary.model_validate(reference),
    )


@router.get("/claims/{claim_id}/recommendations", response_model=list[RecommendationRead])
async def list_recommendations(
    claim_id: uuid.UUID, session: SessionDep, limit: int = Query(default=5, ge=1, le=20)
) -> list[RecommendationRead]:
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Claim {claim_id} not found")

    rows = (
        await session.execute(
            select(CitationRecommendation, ReferencePaper)
            .join(ReferencePaper, ReferencePaper.id == CitationRecommendation.reference_id)
            .where(CitationRecommendation.claim_id == claim_id)
            .order_by(CitationRecommendation.rank)
            .limit(limit)
        )
    ).all()
    return [_serialize(rec, ref) for rec, ref in rows]


async def _get_recommendation(session, recommendation_id: uuid.UUID) -> CitationRecommendation:
    recommendation = (
        await session.execute(
            select(CitationRecommendation)
            .options(selectinload(CitationRecommendation.claim))
            .where(CitationRecommendation.id == recommendation_id)
        )
    ).scalar_one_or_none()
    if recommendation is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Recommendation {recommendation_id} not found"
        )
    return recommendation


@router.post("/recommendations/{recommendation_id}/accept", response_model=RecommendationRead)
async def accept_recommendation(
    recommendation_id: uuid.UUID, session: SessionDep, payload: DecisionRequest | None = None
) -> RecommendationRead:
    recommendation = await _get_recommendation(session, recommendation_id)
    recommendation.user_decision = UserDecision.ACCEPTED
    if payload and payload.note:
        recommendation.user_note = payload.note

    existing = (
        await session.execute(
            select(AcceptedCitation).where(
                AcceptedCitation.claim_id == recommendation.claim_id,
                AcceptedCitation.reference_id == recommendation.reference_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            AcceptedCitation(
                claim_id=recommendation.claim_id,
                reference_id=recommendation.reference_id,
                recommendation_id=recommendation.id,
            )
        )
        await session.flush()

    await _recompute_accepted_citation_texts(session, recommendation.claim.draft_id)
    await session.commit()
    reference = await session.get(ReferencePaper, recommendation.reference_id)
    return _serialize(recommendation, reference)


@router.post("/recommendations/{recommendation_id}/reject", response_model=RecommendationRead)
async def reject_recommendation(
    recommendation_id: uuid.UUID, session: SessionDep, payload: DecisionRequest | None = None
) -> RecommendationRead:
    recommendation = await _get_recommendation(session, recommendation_id)
    recommendation.user_decision = UserDecision.REJECTED
    if payload and payload.note:
        recommendation.user_note = payload.note

    # Accepting then rejecting must not leave a stale accepted citation behind.
    accepted = (
        await session.execute(
            select(AcceptedCitation).where(
                AcceptedCitation.claim_id == recommendation.claim_id,
                AcceptedCitation.reference_id == recommendation.reference_id,
            )
        )
    ).scalar_one_or_none()
    if accepted is not None:
        await session.delete(accepted)
        await session.flush()

    await _recompute_accepted_citation_texts(session, recommendation.claim.draft_id)
    await session.commit()
    reference = await session.get(ReferencePaper, recommendation.reference_id)
    return _serialize(recommendation, reference)
