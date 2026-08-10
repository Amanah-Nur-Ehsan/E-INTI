"""Recommendation pipeline: stages 1-5, top-3 verified rows persisted per claim.

Stages 1-3 are batched *across* claims rather than run per claim: one
`encode` call for every claim's query vector, one `score` call for every
rerank pair. The models are the same and the results are identical -- it
is purely a matter of giving the GPU one large batch instead of N tiny
dispatches, which is where most of the local-model time was going.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
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
from app.services.verification_service import (
    VerdictBatch,
    apply_verification,
    plan_verification,
    run_verification_llm,
)

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


@dataclass
class _ClaimPlan:
    """Everything phase A resolved for one claim, awaiting phase B's LLM
    result. `top` carries the reranker score alongside each candidate
    since stage 5's scoring needs it and phase B/C don't recompute it.
    """

    claim: Claim
    top: list[tuple]
    outcomes: dict
    pending: list


def _plan_claim(
    session: Session, claim: Claim, candidates: list, reranker_scores: list[float]
) -> _ClaimPlan:
    """Stage 4 phase A for one claim: pick the top verify_limit candidates
    by reranker score and resolve everything that doesn't need a call.
    """
    # Sort by reranker score before slicing -- candidates/reranker_scores are
    # zipped in *prerank* order, so slicing candidates[:n] directly would
    # verify the wrong subset (the top-n by prerank, not by reranker).
    ranked = sorted(
        zip(candidates, reranker_scores, strict=True), key=lambda pair: pair[1], reverse=True
    )
    top = ranked[: get_settings().verify_limit]

    # The verified claim text must match what claim_hash was computed from
    # (the source sentence, not the LLM's paraphrase) -- otherwise the cache
    # key and the cached content answer two different questions, and a
    # re-run with a drifted paraphrase would silently return a stale verdict.
    outcomes, pending = plan_verification(
        session, claim.claim_hash or "", [candidate for candidate, _ in top]
    )
    return _ClaimPlan(claim=claim, top=top, outcomes=outcomes, pending=pending)


def _run_claim_llm(plan: _ClaimPlan) -> VerdictBatch | None:
    """Stage 4 phase B for one claim. Pure -- safe to run in a thread pool
    across claims. Skips the call entirely when nothing is pending, rather
    than spending a request (and a thread) to verify zero candidates.
    """
    if not plan.pending:
        return None
    return run_verification_llm(plan.claim.sentence_text, plan.claim.local_context, plan.pending)


def _persist_claim(session: Session, plan: _ClaimPlan, batch: VerdictBatch | None) -> int:
    """Stage 4 phase C + stage 5 for one claim: resolve verdicts, score,
    replace its recommendation rows. No commit -- the caller commits once
    after every claim in the batch has been persisted.
    """
    settings = get_settings()
    model_name = "mock" if settings.llm_mocked else settings.tier2_model
    outcomes = apply_verification(
        session, plan.claim.claim_hash or "", plan.outcomes, plan.pending, batch, model_name
    )

    scored = []
    for candidate, reranker_score in plan.top:
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
        delete(CitationRecommendation).where(CitationRecommendation.claim_id == plan.claim.id)
    )
    for rank, (candidate, outcome, breakdown) in enumerate(scored, start=1):
        session.add(
            CitationRecommendation(
                claim_id=plan.claim.id,
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

    return len(scored)


def recommend_for_claim(
    session: Session,
    claim: Claim,
    corpus: LibraryCorpus,
) -> int:
    """Run stages 1-5 for one claim and persist its top-3. Returns the count.

    A single-claim wrapper over the same passes `recommend_for_draft` uses,
    kept so callers and tests that work one claim at a time still can. The
    LLM call runs directly rather than through a pool -- there is only one
    claim, nothing to parallelize against.
    """
    prepared = _retrieve_and_prerank(session, [claim], corpus)
    if not prepared:
        return 0
    scores = _rerank_all(prepared)
    plan = _plan_claim(session, claim, prepared[0].candidates, scores[0])
    batch = _run_claim_llm(plan)
    total = _persist_claim(session, plan, batch)
    session.commit()
    return total


def recommend_for_draft(session: Session, draft_id: uuid.UUID) -> dict:
    """Stage body: recommend references for every citation-worthy claim.

    The product now shows one ranked shortlist of references for the whole
    draft (see app/api/routes/recommendations.py::best_references), not a
    per-claim citation list -- so running retrieval and verification over
    all 137 claims of a real paper to produce a 3-5 item shortlist is mostly
    wasted work, and it is wasted at *both* stages:

    - Retrieval (stages 1-3, local models) used to run over every
      citation-worthy claim and only afterwards keep the top-scoring ones --
      ~137 SPECTER2 embeddings and ~1,370 cross-encoder pairs to use maybe
      20. settings.retrieve_claim_limit caps entry into retrieval itself,
      picked by Claim.claim_confidence (already computed by Tier-1, free to
      reuse) -- the claims least likely to need a citation at all are also
      the ones with no realistic path into the shortlist.
    - Verification (stage 4, LLM-paced) then further narrows to
      settings.verify_claim_limit by reranked score, unchanged from before.
    """
    settings = get_settings()
    claims = list(
        session.execute(
            select(Claim)
            .where(Claim.draft_id == draft_id, Claim.needs_citation.is_(True))
            .order_by(Claim.char_start)
        ).scalars()
    )
    if not claims:
        return {"claims_processed": 0, "recommendations": 0}

    retrieve_limit = settings.retrieve_claim_limit
    if retrieve_limit and len(claims) > retrieve_limit:
        claims = sorted(claims, key=lambda c: c.claim_confidence or 0.0, reverse=True)
        claims = claims[:retrieve_limit]
        claims.sort(key=lambda c: c.char_start or 0)

    corpus = LibraryCorpus(session)

    # Stages 1-3 batched across every claim.
    prepared = _retrieve_and_prerank(session, claims, corpus)
    all_scores = _rerank_all(prepared)

    # Rank claims by their single best reranked candidate and only verify
    # the top N. A claim whose best candidate isn't even a strong reranker
    # match has no realistic path into a whole-paper top-3-5 shortlist, so
    # spending an LLM call on it buys nothing.
    limit = get_settings().verify_claim_limit
    ranked_items = sorted(
        zip(prepared, all_scores, strict=True),
        key=lambda pair: max(pair[1], default=0.0),
        reverse=True,
    )
    to_verify = ranked_items[:limit]

    # Clear every claim's stale rows up front: a claim that verified last
    # run but falls outside the limit this run (fewer/differently-scored
    # candidates, a changed verify_claim_limit) must not keep old rows.
    prepared_claim_ids = [item.claim.id for item, _ in ranked_items]
    if prepared_claim_ids:
        session.execute(
            delete(CitationRecommendation).where(
                CitationRecommendation.claim_id.in_(prepared_claim_ids)
            )
        )

    # Phase A (session, serial): resolve caches + no-abstract short-circuits
    # for every claim before any LLM call is made.
    plans = [
        _plan_claim(session, item.claim, item.candidates, reranker_scores)
        for item, reranker_scores in to_verify
    ]

    # Phase B (no session, concurrent): each claim's Tier-2 call is
    # independent of every other claim's, so they run in a bounded thread
    # pool instead of one at a time -- this is the actual wall-clock win.
    # pool.map keeps `batches` index-aligned with `plans`.
    if plans:
        with ThreadPoolExecutor(
            max_workers=min(settings.llm_max_concurrency, len(plans))
        ) as pool:
            batches = list(pool.map(_run_claim_llm, plans))
    else:
        batches = []

    # Phase C (session, serial): apply each claim's result and persist.
    # One commit for the whole draft rather than one per claim.
    total = sum(
        _persist_claim(session, plan, batch)
        for plan, batch in zip(plans, batches, strict=True)
    )
    session.commit()

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
