import uuid
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DraftDep, SessionDep
from app.core.config import get_settings
from app.db.models import AcceptedCitation, CitationRecommendation, Claim, ReferencePaper
from app.db.models.enums import UserDecision
from app.schemas.recommendation import (
    BestReferenceClaim,
    BestReferenceRead,
    DecisionRequest,
    ParagraphRewriteRead,
    ParagraphRewriteRequest,
    RecommendationRead,
    ReferenceDetail,
    ReferenceSummary,
    ScoreBreakdownOut,
    SetDecisionRequest,
)
from app.services.citation_formatting_service import (
    SUPPORTED_STYLES,
    build_citation_context,
    join_in_text,
)

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


@router.get("/drafts/{draft_id}/recommendations", response_model=dict[uuid.UUID, list[RecommendationRead]])
async def list_recommendations_for_draft(
    draft: DraftDep, session: SessionDep, limit_per_claim: int = Query(default=5, ge=1, le=20)
) -> dict[uuid.UUID, list[RecommendationRead]]:
    """All recommendations for every claim in a draft, in one request --
    the review screen would otherwise need one round trip per claim
    (55 claims = 55 requests on the real validation paper).
    """
    rows = (
        await session.execute(
            select(CitationRecommendation, ReferencePaper)
            .join(ReferencePaper, ReferencePaper.id == CitationRecommendation.reference_id)
            .join(Claim, Claim.id == CitationRecommendation.claim_id)
            .where(Claim.draft_id == draft.id)
            .order_by(CitationRecommendation.claim_id, CitationRecommendation.rank)
        )
    ).all()

    by_claim: dict[uuid.UUID, list[RecommendationRead]] = defaultdict(list)
    for rec, ref in rows:
        if len(by_claim[rec.claim_id]) < limit_per_claim:
            by_claim[rec.claim_id].append(_serialize(rec, ref))
    return dict(by_claim)


@router.get("/drafts/{draft_id}/best-reference", response_model=BestReferenceRead)
async def best_reference_for_draft(draft: DraftDep, session: SessionDep) -> BestReferenceRead:
    """The single reference this paper should cite: the highest-scoring
    top-ranked recommendation across every claim in the draft. Always
    returns the closest match even if it falls below the usable
    threshold -- an empty response reads as "broken," not "no reference
    is good enough yet," so the caller gets the number and decides.
    """
    row = (
        await session.execute(
            select(CitationRecommendation, ReferencePaper, Claim)
            .join(ReferencePaper, ReferencePaper.id == CitationRecommendation.reference_id)
            .join(Claim, Claim.id == CitationRecommendation.claim_id)
            .where(Claim.draft_id == draft.id, CitationRecommendation.rank == 1)
            .order_by(CitationRecommendation.score_percentage.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No recommendations yet for this draft"
        )

    recommendation, reference, claim = row
    settings = get_settings()
    score = recommendation.score_percentage

    return BestReferenceRead(
        recommendation=_serialize(recommendation, reference),
        claim=BestReferenceClaim.model_validate(claim),
        reference=ReferenceDetail.model_validate(reference),
        meets_threshold=score >= settings.best_reference_min_score,
        is_recommended=score >= settings.best_reference_recommended_score,
        min_score_threshold=settings.best_reference_min_score,
        recommended_score_threshold=settings.best_reference_recommended_score,
    )


@router.get("/drafts/{draft_id}/best-references", response_model=list[BestReferenceRead])
async def best_references_for_draft(
    draft: DraftDep, session: SessionDep, limit: int = Query(default=5, ge=1, le=20)
) -> list[BestReferenceRead]:
    """The N best references for this paper as a whole -- a ranked
    shortlist rather than the single pick /best-reference returns, for
    "which references should I actually cite" instead of "give me one."

    Mirrors /best-reference's query and threshold logic exactly, just
    without the .limit(1): every claim's rank=1 recommendation, ordered by
    score. The same reference can legitimately be the strongest match for
    more than one claim, so rows are deduped by reference_id (keeping each
    reference's highest-scoring claim, since the ordering already put that
    one first) before truncating to `limit` -- otherwise a paper with one
    dominant reference could fill the whole shortlist with itself.
    """
    rows = (
        await session.execute(
            select(CitationRecommendation, ReferencePaper, Claim)
            .join(ReferencePaper, ReferencePaper.id == CitationRecommendation.reference_id)
            .join(Claim, Claim.id == CitationRecommendation.claim_id)
            .where(Claim.draft_id == draft.id, CitationRecommendation.rank == 1)
            .order_by(CitationRecommendation.score_percentage.desc())
        )
    ).all()

    settings = get_settings()
    results: list[BestReferenceRead] = []
    seen_reference_ids: set[uuid.UUID] = set()
    for recommendation, reference, claim in rows:
        if reference.id in seen_reference_ids:
            continue
        seen_reference_ids.add(reference.id)

        score = recommendation.score_percentage
        results.append(
            BestReferenceRead(
                recommendation=_serialize(recommendation, reference),
                claim=BestReferenceClaim.model_validate(claim),
                reference=ReferenceDetail.model_validate(reference),
                meets_threshold=score >= settings.best_reference_min_score,
                is_recommended=score >= settings.best_reference_recommended_score,
                min_score_threshold=settings.best_reference_min_score,
                recommended_score_threshold=settings.best_reference_recommended_score,
            )
        )
        if len(results) >= limit:
            break

    return results


@router.get("/drafts/{draft_id}/accepted-citations", response_model=dict[uuid.UUID, str])
async def accepted_citations_for_draft(draft: DraftDep, session: SessionDep) -> dict[uuid.UUID, str]:
    """claim_id -> the joined citation text ghost text should render, e.g.
    "(Smith, 2023; Lee et al., 2024)" when a claim has multiple accepted
    references. Kept separate from the recommendations payload since it's
    a per-claim aggregate rather than a per-recommendation field.
    """
    rows = (
        await session.execute(
            select(AcceptedCitation.claim_id, AcceptedCitation.citation_text)
            .join(Claim, Claim.id == AcceptedCitation.claim_id)
            .where(Claim.draft_id == draft.id)
            .order_by(AcceptedCitation.created_at)
        )
    ).all()

    by_claim: dict[uuid.UUID, list[str]] = defaultdict(list)
    for claim_id, citation_text in rows:
        if citation_text:
            by_claim[claim_id].append(citation_text)
    return {claim_id: join_in_text(texts) for claim_id, texts in by_claim.items()}


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


@router.post(
    "/recommendations/{recommendation_id}/rewrite-paragraph", response_model=ParagraphRewriteRead
)
async def rewrite_paragraph_for_recommendation(
    recommendation_id: uuid.UUID, payload: ParagraphRewriteRequest, session: SessionDep
) -> ParagraphRewriteRead:
    """Generate a version of the claim's paragraph with this reference's
    citation woven in, plus the bibliography entry to go with it -- for
    the "help me actually write the cited paragraph" ask, not just "here
    is a reference you could use."
    """
    style = (payload.style or "APA").strip().upper()
    if style not in SUPPORTED_STYLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"style must be one of {', '.join(sorted(SUPPORTED_STYLES))} (got {payload.style!r})",
        )

    recommendation = await _get_recommendation(session, recommendation_id)
    reference = await session.get(ReferencePaper, recommendation.reference_id)
    if reference is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reference no longer exists")
    claim = recommendation.claim

    context = build_citation_context([reference], style=style)
    in_text_citation = context.in_text(reference.id)
    bibliography_entry = "".join(seg.text for seg in context.entry(reference.id))

    import anyio

    from app.services.paragraph_rewrite_service import rewrite_paragraph

    try:
        paragraph = await anyio.to_thread.run_sync(
            rewrite_paragraph, claim.local_context, claim.sentence_text, in_text_citation
        )
    except Exception as exc:
        from app.services.llm_client import LLMOutputError

        if isinstance(exc, LLMOutputError):
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, f"Could not generate the paragraph: {exc}"
            ) from exc
        raise

    return ParagraphRewriteRead(
        paragraph=paragraph,
        in_text_citation=in_text_citation,
        bibliography_entry=bibliography_entry,
        style=style,
    )


async def _apply_decision(
    session, recommendation: CitationRecommendation, decision: str, note: str | None
) -> RecommendationRead:
    recommendation.user_decision = decision
    if note is not None:
        recommendation.user_note = note

    existing = (
        await session.execute(
            select(AcceptedCitation).where(
                AcceptedCitation.claim_id == recommendation.claim_id,
                AcceptedCitation.reference_id == recommendation.reference_id,
            )
        )
    ).scalar_one_or_none()

    if decision == UserDecision.ACCEPTED:
        if existing is None:
            session.add(
                AcceptedCitation(
                    claim_id=recommendation.claim_id,
                    reference_id=recommendation.reference_id,
                    recommendation_id=recommendation.id,
                )
            )
            await session.flush()
    else:
        # REJECTED or IRRELEVANT: an existing acceptance must not survive
        # a change of mind.
        if existing is not None:
            await session.delete(existing)
            await session.flush()

    await _recompute_accepted_citation_texts(session, recommendation.claim.draft_id)
    await session.commit()
    reference = await session.get(ReferencePaper, recommendation.reference_id)
    return _serialize(recommendation, reference)


@router.post("/recommendations/{recommendation_id}/decision", response_model=RecommendationRead)
async def set_recommendation_decision(
    recommendation_id: uuid.UUID, payload: SetDecisionRequest, session: SessionDep
) -> RecommendationRead:
    if payload.decision not in (UserDecision.ACCEPTED, UserDecision.REJECTED, UserDecision.IRRELEVANT):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"decision must be one of ACCEPTED, REJECTED, IRRELEVANT (got {payload.decision!r})",
        )
    recommendation = await _get_recommendation(session, recommendation_id)
    return await _apply_decision(session, recommendation, payload.decision, payload.note)


@router.post("/recommendations/{recommendation_id}/accept", response_model=RecommendationRead)
async def accept_recommendation(
    recommendation_id: uuid.UUID, session: SessionDep, payload: DecisionRequest | None = None
) -> RecommendationRead:
    recommendation = await _get_recommendation(session, recommendation_id)
    return await _apply_decision(
        session, recommendation, UserDecision.ACCEPTED, payload.note if payload else None
    )


@router.post("/recommendations/{recommendation_id}/reject", response_model=RecommendationRead)
async def reject_recommendation(
    recommendation_id: uuid.UUID, session: SessionDep, payload: DecisionRequest | None = None
) -> RecommendationRead:
    recommendation = await _get_recommendation(session, recommendation_id)
    return await _apply_decision(
        session, recommendation, UserDecision.REJECTED, payload.note if payload else None
    )
