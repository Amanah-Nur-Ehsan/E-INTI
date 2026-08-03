"""Tier-2 verification sends one batched call per claim rather than one
per candidate, and degrades safely when that batch comes back wrong.

The batching is the point (3x fewer requests at verify_limit=3), but the
failure modes are what actually needs guarding: a missing or out-of-range
idx must never silently attach one candidate's verdict to another, and a
SKIPPED verdict must never be cached -- otherwise a transient outage
would be frozen into the cache and returned forever.
"""

import pytest

from app.db.models import LLMVerificationCache, ReferencePaper
from app.db.models.enums import Verdict
from app.services.llm_client import LLMOutputError
from app.services.retrieval_service import Candidate
from app.services.verification_service import verify_candidates

pytestmark = pytest.mark.integration

CLAIM = "Machine learning improves fraud detection accuracy in payment systems."
ABSTRACT = (
    "We evaluate machine learning models for fraud detection in payment systems and "
    "report improved accuracy over rule engines across several transaction datasets."
)


def _make_reference(db_session, title: str, abstract: str | None) -> ReferencePaper:
    reference = ReferencePaper(title=title, abstract=abstract, original_data={})
    db_session.add(reference)
    db_session.commit()
    db_session.refresh(reference)
    return reference


def _candidate(reference: ReferencePaper) -> Candidate:
    return Candidate(
        reference_id=reference.id,
        title=reference.title,
        abstract=reference.abstract,
    )


class _CountingClient:
    """Wraps the mock client so calls can be counted per test."""

    def __init__(self):
        from app.services.mocks.mock_llm import MockLLMClient

        self._inner = MockLLMClient()
        self.calls = 0

    def complete_structured(self, **kwargs):
        self.calls += 1
        return self._inner.complete_structured(**kwargs)


class _FailingClient:
    def __init__(self):
        self.calls = 0

    def complete_structured(self, **kwargs):
        self.calls += 1
        raise LLMOutputError("verifier unavailable")


class _PartialClient:
    """Answers only the first candidate, and adds one bogus out-of-range idx."""

    def __init__(self):
        self.calls = 0

    def complete_structured(self, *, tier, system, user, schema):  # noqa: ARG002
        self.calls += 1
        return schema.model_validate(
            {
                "verdicts": [
                    {
                        "idx": 0,
                        "verdict": "SUPPORTED",
                        "support_strength": 0.9,
                        "supporting_evidence": "evidence",
                        "limitations": "",
                        "recommended_usage": "Direct citation",
                    },
                    {
                        "idx": 99,  # out of range -- must be dropped, not applied
                        "verdict": "CONTRADICTED",
                        "support_strength": 0.0,
                        "supporting_evidence": "bogus",
                        "limitations": "",
                        "recommended_usage": "Do not cite",
                    },
                ]
            }
        )


def test_three_candidates_take_one_call_not_three(db_session, monkeypatch):
    refs = [_make_reference(db_session, f"Paper {i}", ABSTRACT) for i in range(3)]
    client = _CountingClient()
    monkeypatch.setattr("app.services.verification_service.get_llm_client", lambda: client)

    outcomes = verify_candidates(
        db_session,
        claim_text=CLAIM,
        claim_context=CLAIM,
        claim_hash="hash-one-call",
        candidates=[_candidate(r) for r in refs],
    )

    assert client.calls == 1
    assert len(outcomes) == 3
    assert all(o.verdict is not Verdict.SKIPPED for o in outcomes.values())

    cached = db_session.query(LLMVerificationCache).filter_by(claim_hash="hash-one-call").all()
    assert len(cached) == 3
    assert {row.reference_id for row in cached} == {r.id for r in refs}


def test_no_abstract_candidates_never_reach_the_model(db_session, monkeypatch):
    with_abstract = _make_reference(db_session, "Has abstract", ABSTRACT)
    without = _make_reference(db_session, "No abstract", None)
    client = _CountingClient()
    monkeypatch.setattr("app.services.verification_service.get_llm_client", lambda: client)

    outcomes = verify_candidates(
        db_session,
        claim_text=CLAIM,
        claim_context=CLAIM,
        claim_hash="hash-no-abstract",
        candidates=[_candidate(with_abstract), _candidate(without)],
    )

    assert client.calls == 1  # only the one with an abstract went in the batch
    assert outcomes[without.id].verdict is Verdict.INSUFFICIENT_EVIDENCE
    assert "No abstract" in outcomes[without.id].limitations


def test_fully_cached_claim_makes_zero_calls(db_session, monkeypatch):
    refs = [_make_reference(db_session, f"Cached {i}", ABSTRACT) for i in range(2)]
    candidates = [_candidate(r) for r in refs]

    first = _CountingClient()
    monkeypatch.setattr("app.services.verification_service.get_llm_client", lambda: first)
    verify_candidates(
        db_session,
        claim_text=CLAIM,
        claim_context=CLAIM,
        claim_hash="hash-cached",
        candidates=candidates,
    )
    assert first.calls == 1

    second = _CountingClient()
    monkeypatch.setattr("app.services.verification_service.get_llm_client", lambda: second)
    outcomes = verify_candidates(
        db_session,
        claim_text=CLAIM,
        claim_context=CLAIM,
        claim_hash="hash-cached",
        candidates=candidates,
    )

    assert second.calls == 0
    assert all(o.from_cache for o in outcomes.values())


def test_batch_failure_skips_every_candidate_and_caches_nothing(db_session, monkeypatch):
    refs = [_make_reference(db_session, f"Fail {i}", ABSTRACT) for i in range(3)]
    monkeypatch.setattr(
        "app.services.verification_service.get_llm_client", lambda: _FailingClient()
    )

    outcomes = verify_candidates(
        db_session,
        claim_text=CLAIM,
        claim_context=CLAIM,
        claim_hash="hash-failure",
        candidates=[_candidate(r) for r in refs],
    )

    assert all(o.verdict is Verdict.SKIPPED for o in outcomes.values())
    # Nothing cached: a transient outage must not freeze SKIPPED forever.
    assert db_session.query(LLMVerificationCache).filter_by(claim_hash="hash-failure").count() == 0


def test_missing_verdict_skips_only_that_candidate(db_session, monkeypatch):
    answered = _make_reference(db_session, "Answered", ABSTRACT)
    unanswered = _make_reference(db_session, "Unanswered", ABSTRACT)
    monkeypatch.setattr(
        "app.services.verification_service.get_llm_client", lambda: _PartialClient()
    )

    outcomes = verify_candidates(
        db_session,
        claim_text=CLAIM,
        claim_context=CLAIM,
        claim_hash="hash-partial",
        candidates=[_candidate(answered), _candidate(unanswered)],
    )

    assert outcomes[answered.id].verdict is Verdict.SUPPORTED
    assert outcomes[unanswered.id].verdict is Verdict.SKIPPED

    # The out-of-range idx=99 verdict must not have leaked onto anyone.
    assert all(o.verdict is not Verdict.CONTRADICTED for o in outcomes.values())

    cached = db_session.query(LLMVerificationCache).filter_by(claim_hash="hash-partial").all()
    assert [row.reference_id for row in cached] == [answered.id]


def test_verdicts_map_to_the_right_reference(db_session, monkeypatch):
    """Index-to-candidate mapping is the whole risk of batching: a shifted
    mapping would attach a verdict to the wrong paper, invisibly.
    """
    supporting = _make_reference(db_session, "Directly on topic", ABSTRACT)
    unrelated = _make_reference(
        db_session,
        "Sonnet structure in renaissance poetry",
        "We analyse rhyme schemes across sixteenth century sonnets.",
    )
    monkeypatch.setattr(
        "app.services.verification_service.get_llm_client", lambda: _CountingClient()
    )

    outcomes = verify_candidates(
        db_session,
        claim_text=CLAIM,
        claim_context=CLAIM,
        claim_hash="hash-mapping",
        candidates=[_candidate(supporting), _candidate(unrelated)],
    )

    # The mock scores by lexical overlap, so the on-topic paper must land
    # strictly above the unrelated one -- proving idx wasn't transposed.
    assert outcomes[supporting.id].support_score > outcomes[unrelated.id].support_score
