"""Recommendation pipeline: stages 1-5 per claim, top-5 persisted."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import CitationRecommendation, Claim, Project
from app.db.models.enums import Verdict
from app.services.embedding_service import claim_embedding_text, get_embedding_service
from app.services.reranking_service import build_pair, get_reranking_service
from app.services.retrieval_service import (
    RERANK_LIMIT,
    RETRIEVAL_LIMIT,
    ProjectCorpus,
    prerank,
    vector_search,
)
from app.services.scoring import compute_score
from app.services.verification_service import verify_candidates

log = get_logger(__name__)


def recommend_for_claim(
    session: Session,
    project: Project,
    claim: Claim,
    corpus: ProjectCorpus,
) -> int:
    """Run stages 1-5 for one claim and persist its top-5. Returns the count."""
    embedder = get_embedding_service()
    reranker = get_reranking_service()

    query_text = claim_embedding_text(claim.claim_text or claim.sentence_text, claim.local_context)
    query_vector = embedder.encode_one(query_text)

    # Stage 1: vector retrieval.
    candidates = vector_search(session, project.id, query_vector, limit=RETRIEVAL_LIMIT)
    if not candidates:
        return 0

    # Stage 2: hybrid pre-ranking down to the rerank set.
    candidates = prerank(
        candidates,
        corpus,
        query=query_text,
        claim_keywords=list(claim.keywords or []),
        project_field=project.field_of_study,
        limit=RERANK_LIMIT,
    )

    # Stage 3: cross-encoder reranking.
    pairs = [build_pair(claim.local_context, c.title, c.abstract) for c in candidates]
    reranker_scores = reranker.score(pairs)

    # Sort by reranker score before slicing -- candidates/reranker_scores are
    # zipped in *prerank* order, so slicing candidates[:n] directly would
    # verify the wrong subset (the top-n by prerank, not by reranker).
    ranked = sorted(
        zip(candidates, reranker_scores, strict=True), key=lambda pair: pair[1], reverse=True
    )
    top = ranked[: get_settings().verify_limit]

    # Stage 4: semantic support verification (cached). Verifying only the
    # top VERIFY_LIMIT (not every reranked candidate) is what keeps a
    # single claim from costing 10 Tier-2 calls when only a handful are
    # ever going to be shown.
    # The verified claim text must match what claim_hash was computed from
    # (the source sentence, not the LLM's paraphrase) -- otherwise the cache
    # key and the cached content answer two different questions, and a
    # re-run with a drifted paraphrase would silently return a stale verdict.
    outcomes = verify_candidates(
        session,
        claim_text=claim.sentence_text,
        claim_context=claim.local_context,
        claim_hash=claim.claim_hash or "",
        candidates=[candidate for candidate, _ in top],
    )

    # Stage 5: final score with caps.
    scored = []
    for candidate, reranker_score in top:
        outcome = outcomes[candidate.reference_id]
        breakdown = compute_score(
            semantic_similarity=candidate.semantic_similarity,
            lexical_similarity=candidate.lexical_similarity,
            keyword_overlap=candidate.keyword_overlap,
            reranker_score=reranker_score,
            llm_support_score=outcome.support_score if outcome.scored else None,
            verdict=outcome.verdict,
            has_abstract=candidate.has_abstract,
        )
        scored.append((candidate, outcome, breakdown))

    # Every candidate here was verified, so all scores share the same basis
    # -- unlike before, this sort never mixes verified and unverified rows.
    scored.sort(key=lambda item: item[2].score_percentage, reverse=True)

    session.execute(
        delete(CitationRecommendation).where(CitationRecommendation.claim_id == claim.id)
    )
    for rank, (candidate, outcome, breakdown) in enumerate(scored, start=1):
        session.add(
            CitationRecommendation(
                claim_id=claim.id,
                reference_id=candidate.reference_id,
                rank=rank,
                semantic_similarity=candidate.semantic_similarity,
                lexical_similarity=candidate.lexical_similarity,
                keyword_overlap=candidate.keyword_overlap,
                field_match=candidate.field_match,
                reranker_score=breakdown.reranker_score,
                llm_support_score=breakdown.llm_support_score,
                final_score=breakdown.final_score,
                score_percentage=breakdown.score_percentage,
                recommendation_label=breakdown.label,
                verdict=outcome.verdict.value,
                recommended_usage=outcome.recommended_usage,
                evidence_paraphrase=outcome.evidence,
                limitations=outcome.limitations,
            )
        )

    session.commit()
    return len(scored)


def recommend_for_draft(session: Session, project_id: uuid.UUID, draft_id: uuid.UUID) -> dict:
    """Stage body: recommend references for every citation-worthy claim."""
    project = session.get(Project, project_id)
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    claims = list(
        session.execute(
            select(Claim)
            .where(Claim.draft_id == draft_id, Claim.needs_citation.is_(True))
            .order_by(Claim.char_start)
        ).scalars()
    )
    if not claims:
        return {"claims_processed": 0, "recommendations": 0}

    corpus = ProjectCorpus(session, project_id)
    total = 0
    for claim in claims:
        total += recommend_for_claim(session, project, claim, corpus)

    return {"claims_processed": len(claims), "recommendations": total}


def verdict_counts(session: Session, draft_id: uuid.UUID) -> dict[str, int]:
    rows = session.execute(
        select(CitationRecommendation.verdict, CitationRecommendation.id)
        .join(Claim, Claim.id == CitationRecommendation.claim_id)
        .where(Claim.draft_id == draft_id)
    ).all()
    counts: dict[str, int] = {v.value: 0 for v in Verdict}
    for verdict, _ in rows:
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts
