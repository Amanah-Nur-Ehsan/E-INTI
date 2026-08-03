"""Recommendation pipeline: stages 1-5, top-3 verified rows persisted per claim.

Stages 1-3 are batched *across* claims rather than run per claim: one
`encode` call for every claim's query vector, one `score` call for every
rerank pair. The models are the same and the results are identical -- it
is purely a matter of giving the GPU one large batch instead of N tiny
dispatches, which is where most of the local-model time was going.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import CitationRecommendation, Claim
from app.db.models.enums import Verdict
from app.services.embedding_service import claim_embedding_text, get_embedding_service
from app.services.reranking_service import build_pair, get_reranking_service
from app.services.retrieval_service import (
    RERANK_LIMIT,
    RETRIEVAL_LIMIT,
    LibraryCorpus,
    prerank,
    vector_search,
)
from app.services.scoring import compute_score
from app.services.verification_service import verify_candidates

log = get_logger(__name__)

#: Rerank pairs per cross-encoder forward pass. Large enough that a
#: multi-claim draft is a handful of batches rather than one per claim,
#: small enough to bound peak memory on CPU-only deployments.
RERANK_BATCH_SIZE = 128


@dataclass
class _ClaimCandidates:
    """One claim's preranked candidates, awaiting reranker scores."""

    claim: Claim
    candidates: list


def _retrieve_and_prerank(
    session: Session, claims: list[Claim], corpus: LibraryCorpus
) -> list[_ClaimCandidates]:
    """Stages 1-2 for every claim, with all query vectors encoded at once."""
    embedder = get_embedding_service()
    query_texts = [
        claim_embedding_text(claim.claim_text or claim.sentence_text, claim.local_context)
        for claim in claims
    ]
    query_vectors = embedder.encode(query_texts)

    prepared: list[_ClaimCandidates] = []
    for claim, query_text, query_vector in zip(claims, query_texts, query_vectors, strict=True):
        candidates = vector_search(session, query_vector, limit=RETRIEVAL_LIMIT)
        if not candidates:
            continue
        prepared.append(
            _ClaimCandidates(
                claim=claim,
                candidates=prerank(
                    candidates,
                    corpus,
                    query=query_text,
                    claim_keywords=list(claim.keywords or []),
                    limit=RERANK_LIMIT,
                ),
            )
        )
    return prepared


def _rerank_all(prepared: list[_ClaimCandidates]) -> list[list[float]]:
    """Stage 3 for every claim in as few cross-encoder passes as possible.

    Pairs from all claims are concatenated, scored, then sliced back apart
    in the same order -- so each claim gets exactly the scores it would
    have got on its own.
    """
    reranker = get_reranking_service()
    pairs: list[tuple[str, str]] = []
    for item in prepared:
        pairs.extend(
            build_pair(item.claim.local_context, c.title, c.abstract) for c in item.candidates
        )

    scores: list[float] = []
    for start in range(0, len(pairs), RERANK_BATCH_SIZE):
        scores.extend(reranker.score(pairs[start : start + RERANK_BATCH_SIZE]))

    sliced: list[list[float]] = []
    offset = 0
    for item in prepared:
        count = len(item.candidates)
        sliced.append(scores[offset : offset + count])
        offset += count
    return sliced


def _verify_and_persist(
    session: Session, claim: Claim, candidates: list, reranker_scores: list[float]
) -> int:
    """Stages 4-5 for one claim: verify, score, replace its rows."""
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


def recommend_for_claim(
    session: Session,
    claim: Claim,
    corpus: LibraryCorpus,
) -> int:
    """Run stages 1-5 for one claim and persist its top-3. Returns the count.

    A single-claim wrapper over the same passes `recommend_for_draft` uses,
    kept so callers and tests that work one claim at a time still can.
    """
    prepared = _retrieve_and_prerank(session, [claim], corpus)
    if not prepared:
        return 0
    scores = _rerank_all(prepared)
    return _verify_and_persist(session, claim, prepared[0].candidates, scores[0])


def recommend_for_draft(session: Session, draft_id: uuid.UUID) -> dict:
    """Stage body: recommend references for every citation-worthy claim."""
    claims = list(
        session.execute(
            select(Claim)
            .where(Claim.draft_id == draft_id, Claim.needs_citation.is_(True))
            .order_by(Claim.char_start)
        ).scalars()
    )
    if not claims:
        return {"claims_processed": 0, "recommendations": 0}

    corpus = LibraryCorpus(session)

    # Stages 1-3 batched across every claim, then stages 4-5 per claim --
    # the LLM calls in stage 4 stay serial because they are what the rate
    # limiter paces.
    prepared = _retrieve_and_prerank(session, claims, corpus)
    all_scores = _rerank_all(prepared)

    total = 0
    for item, reranker_scores in zip(prepared, all_scores, strict=True):
        total += _verify_and_persist(session, item.claim, item.candidates, reranker_scores)

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
