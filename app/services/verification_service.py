"""Stage 4: semantic support verification (Tier 2), with caching.

This is the layer that stops a topically perfect paper from being presented
as evidence it does not contain. Two rules matter more than throughput:

* A reference with no abstract is never sent to the model — there is
  nothing to verify, so the verdict is INSUFFICIENT_EVIDENCE by construction.
* If the model is unreachable or keeps producing invalid output, the verdict
  is SKIPPED and the LLM term is dropped from the score. Never a guess.

Results are cached on (claim_hash, reference_id) so editing one paragraph
does not re-verify the rest of the draft.
"""

import uuid
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import LLMVerificationCache
from app.db.models.enums import SUPPORT_SCORE, Verdict
from app.services.llm_client import LLMOutputError, Tier, get_llm_client
from app.services.retrieval_service import Candidate

log = get_logger(__name__)

VERIFY_SYSTEM = """You are a strict academic citation verifier.

Evaluate whether the candidate reference can legitimately support the claim.

Rules:
1. Use only the supplied title, abstract, and keywords.
2. Do not infer study results that are not present in the abstract.
3. A topic match alone is not sufficient.
4. Mark SUPPORTED only if the abstract explicitly or strongly semantically supports the claim.
5. Mark PARTIALLY_SUPPORTED if the paper supports only part of the claim.
6. Mark TOPICALLY_RELATED_BUT_NOT_EVIDENCE if topics overlap but the abstract does not establish the claim.
7. Mark INSUFFICIENT_EVIDENCE if the abstract lacks enough information.
8. Mark CONTRADICTED if the abstract conflicts with the claim.

Never quote the abstract verbatim; paraphrase the relevant evidence in your own words.

Return JSON only."""

VERIFY_USER_TEMPLATE = """CLAIM: {claim}
CONTEXT: {context}

Judge every candidate below independently against that one claim.

{candidates}
Respond with JSON: {{"verdicts": [one entry per candidate, in any order]}}, each entry:
{{"idx": <candidate number>,
"verdict": "SUPPORTED|PARTIALLY_SUPPORTED|TOPICALLY_RELATED_BUT_NOT_EVIDENCE|INSUFFICIENT_EVIDENCE|CONTRADICTED",
"support_strength": <0.0-1.0>, "supporting_evidence": "<short paraphrase>",
"limitations": "<what is not supported>", "recommended_usage": "Direct citation|Background citation|Do not cite"}}"""

VERIFY_CANDIDATE_TEMPLATE = """CANDIDATE {idx}
TITLE: {title}
ABSTRACT: {abstract}
KEYWORDS: {keywords}
"""


class SupportVerdict(BaseModel):
    verdict: Verdict
    support_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    supporting_evidence: str = ""
    limitations: str = ""
    recommended_usage: str = ""


class CandidateVerdict(SupportVerdict):
    """A SupportVerdict tagged with which candidate it answers.

    Subclasses rather than wraps so `_outcome_from_verdict` keeps working
    unchanged on either shape.
    """

    idx: int


class VerdictBatch(BaseModel):
    verdicts: list[CandidateVerdict]


@dataclass
class VerificationOutcome:
    verdict: Verdict
    support_score: float
    evidence: str
    limitations: str
    recommended_usage: str
    from_cache: bool = False

    @property
    def scored(self) -> bool:
        """False when verification could not run — the LLM term is then dropped."""
        return self.verdict is not Verdict.SKIPPED


def _missing_abstract_outcome() -> VerificationOutcome:
    return VerificationOutcome(
        verdict=Verdict.INSUFFICIENT_EVIDENCE,
        support_score=SUPPORT_SCORE[Verdict.INSUFFICIENT_EVIDENCE],
        evidence="",
        limitations="No abstract could be retrieved for this reference, so its support cannot be assessed.",
        recommended_usage="Do not cite without checking the full text",
    )


def _outcome_from_verdict(result: SupportVerdict) -> VerificationOutcome:
    return VerificationOutcome(
        verdict=result.verdict,
        support_score=SUPPORT_SCORE.get(result.verdict, 0.0),
        evidence=result.supporting_evidence,
        limitations=result.limitations,
        recommended_usage=result.recommended_usage,
    )


def _load_cache(
    session: Session, claim_hash: str, reference_ids: list[uuid.UUID]
) -> dict[uuid.UUID, VerificationOutcome]:
    if not reference_ids:
        return {}
    rows = session.execute(
        select(LLMVerificationCache).where(
            LLMVerificationCache.claim_hash == claim_hash,
            LLMVerificationCache.reference_id.in_(reference_ids),
        )
    ).scalars()

    cached: dict[uuid.UUID, VerificationOutcome] = {}
    for row in rows:
        payload = row.payload or {}
        verdict = Verdict(row.verdict)
        cached[row.reference_id] = VerificationOutcome(
            verdict=verdict,
            support_score=SUPPORT_SCORE.get(verdict, 0.0),
            evidence=payload.get("supporting_evidence", ""),
            limitations=payload.get("limitations", ""),
            recommended_usage=payload.get("recommended_usage", ""),
            from_cache=True,
        )
    return cached


def _store_cache(
    session: Session,
    claim_hash: str,
    reference_id: uuid.UUID,
    outcome: VerificationOutcome,
    model: str,
) -> None:
    session.execute(
        pg_insert(LLMVerificationCache)
        .values(
            id=uuid.uuid4(),
            claim_hash=claim_hash,
            reference_id=reference_id,
            verdict=outcome.verdict.value,
            payload={
                "supporting_evidence": outcome.evidence,
                "limitations": outcome.limitations,
                "recommended_usage": outcome.recommended_usage,
            },
            model=model,
        )
        .on_conflict_do_nothing(index_elements=["claim_hash", "reference_id"])
    )


def _skipped_outcome() -> VerificationOutcome:
    return VerificationOutcome(
        verdict=Verdict.SKIPPED,
        support_score=0.0,
        evidence="",
        limitations="Automatic verification was unavailable for this candidate.",
        recommended_usage="Review manually",
    )


def plan_verification(
    session: Session, claim_hash: str, candidates: list[Candidate]
) -> tuple[dict[uuid.UUID, VerificationOutcome], list[Candidate]]:
    """Phase A: cache lookups + the no-abstract short-circuit.

    The only phase that touches the session, and the only one that must
    run before any LLM call -- splitting it out is what lets the LLM call
    (phase B, run_verification_llm) run in a thread pool alongside other
    claims' calls without touching a SQLAlchemy session from a worker
    thread. Returns the outcomes already resolved without a call, and the
    candidates still needing one. No commit; the caller commits once after
    persisting every claim in a batch (see recommendation_pipeline.py).
    """
    outcomes = _load_cache(session, claim_hash, [c.reference_id for c in candidates])

    pending: list[Candidate] = []
    for candidate in candidates:
        if candidate.reference_id in outcomes:
            continue
        if not candidate.has_abstract:
            # Nothing to read: don't spend a call, and never guess support.
            outcomes[candidate.reference_id] = _missing_abstract_outcome()
            continue
        pending.append(candidate)

    return outcomes, pending


def run_verification_llm(
    claim_text: str, claim_context: str, pending: list[Candidate]
) -> VerdictBatch | None:
    """Phase B: the LLM call alone. Pure -- no session, no cache access --
    which is what makes it safe to run concurrently across claims in a
    thread pool. Call only when `pending` is non-empty; `None` means the
    whole batch failed (transport retries and the Gemini fallback both
    exhausted), which apply_verification degrades to SKIPPED for every
    candidate in it rather than inventing a verdict.
    """
    # Batch-local numbering 0..n-1, mapped back via `pending[idx]` -- models
    # renumber sequentially regardless of what they are given, so this is
    # the only mapping that survives (same discipline as classify_batch).
    blocks = "\n".join(
        VERIFY_CANDIDATE_TEMPLATE.format(
            idx=idx,
            title=candidate.title,
            abstract=candidate.abstract,
            keywords="; ".join(
                (candidate.author_keywords or []) + (candidate.index_keywords or [])
            ),
        )
        for idx, candidate in enumerate(pending)
    )
    user = VERIFY_USER_TEMPLATE.format(claim=claim_text, context=claim_context, candidates=blocks)

    try:
        return get_llm_client().complete_structured(
            tier=Tier.VERIFY, system=VERIFY_SYSTEM, user=user, schema=VerdictBatch
        )
    except LLMOutputError as exc:
        log.warning("verification_unavailable", candidates=len(pending), error=str(exc))
        return None


def apply_verification(
    session: Session,
    claim_hash: str,
    outcomes: dict[uuid.UUID, VerificationOutcome],
    pending: list[Candidate],
    batch: VerdictBatch | None,
    model_name: str,
) -> dict[uuid.UUID, VerificationOutcome]:
    """Phase C: turn phase B's result into outcomes and cache rows.

    Mutates and returns `outcomes` (phase A's dict) so cached and
    freshly-verified candidates end up in the same mapping. No commit --
    same reason as plan_verification.
    """
    if batch is None:
        # Covers both "the call failed" and "there was nothing pending" --
        # identical no-op behavior when `pending` is empty either way, so
        # callers don't need a distinct sentinel for the two.
        for candidate in pending:
            outcomes[candidate.reference_id] = _skipped_outcome()
        return outcomes

    by_idx: dict[int, CandidateVerdict] = {}
    for verdict in batch.verdicts:
        if 0 <= verdict.idx < len(pending):
            by_idx[verdict.idx] = verdict
        else:
            log.warning("verdict_index_out_of_range", idx=verdict.idx, batch=len(pending))

    for idx, candidate in enumerate(pending):
        verdict = by_idx.get(idx)
        if verdict is None:
            # The model answered the batch but skipped this one; treat it
            # exactly like a failed call rather than inventing a verdict.
            log.warning("verdict_missing", reference_id=str(candidate.reference_id))
            outcomes[candidate.reference_id] = _skipped_outcome()
            continue
        outcome = _outcome_from_verdict(verdict)
        outcomes[candidate.reference_id] = outcome
        _store_cache(session, claim_hash, candidate.reference_id, outcome, model_name)

    return outcomes


def verify_candidates(
    session: Session,
    claim_text: str,
    claim_context: str,
    claim_hash: str,
    candidates: list[Candidate],
) -> dict[uuid.UUID, VerificationOutcome]:
    """Verify each candidate, consulting and populating the cache.

    Every candidate needing the model goes in a *single* Tier-2 call
    rather than one call each: at verify_limit=3 that is 3x fewer
    requests against the rate limit, and fewer tokens too, since the
    system prompt and the claim are sent once instead of per candidate.

    A thin wrapper over the three phases above, for callers that verify
    one claim in isolation (recommend_for_claim, this module's own tests).
    recommend_for_draft calls plan_verification / run_verification_llm /
    apply_verification directly so phase B can run concurrently across
    claims instead of one call at a time.
    """
    settings = get_settings()
    model_name = "mock" if settings.llm_mocked else settings.tier2_model

    outcomes, pending = plan_verification(session, claim_hash, candidates)
    if not pending:
        session.commit()
        return outcomes

    batch = run_verification_llm(claim_text, claim_context, pending)
    outcomes = apply_verification(session, claim_hash, outcomes, pending, batch, model_name)
    session.commit()
    return outcomes
