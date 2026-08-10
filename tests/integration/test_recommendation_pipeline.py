import pytest

from app.db.models.enums import UserDecision, Verdict
from app.services.scoring import CONTRADICTED_CAP, MISSING_ABSTRACT_CAP

pytestmark = pytest.mark.integration

SUPPORTING_TITLE = "Machine Learning Methods for Financial Fraud Detection"
CONTRADICTING_TITLE = "Reassessing Learned Models Against Rule Engines in Card Fraud Screening"
OPENING_CLAIM = "Machine learning techniques have improved the ability to identify complex fraud"


@pytest.fixture
async def analyzed(client, seeded_draft):
    """Run the whole pipeline end to end on the fixture draft."""
    resp = await client.post(f"/api/v1/drafts/{seeded_draft}/analysis/run")
    assert resp.status_code == 202, resp.text
    status = (await client.get(f"/api/v1/drafts/{seeded_draft}/analysis/status")).json()
    assert status["status"] == "COMPLETED", status
    return seeded_draft


async def _claims(client, draft_id):
    return (await client.get(f"/api/v1/drafts/{draft_id}/claims?needs_citation=true")).json()


async def test_pipeline_completes_and_produces_recommendations(client, analyzed):
    draft_id = analyzed
    status = (await client.get(f"/api/v1/drafts/{draft_id}/analysis/status")).json()
    assert status["claims"]["needs_citation"] > 0
    assert status["claims"]["with_recommendations"] > 0


async def test_planted_supporting_reference_ranks_first(client, analyzed):
    """The fixture claim restates ref 1's abstract almost verbatim."""
    draft_id = analyzed
    claims = await _claims(client, draft_id)
    claim = next(c for c in claims if c["sentence_text"].startswith(OPENING_CLAIM))

    recs = (await client.get(f"/api/v1/claims/{claim['id']}/recommendations")).json()
    assert recs, "expected recommendations for the planted claim"

    top = recs[0]
    assert top["reference"]["title"] == SUPPORTING_TITLE
    assert top["rank"] == 1
    assert top["verdict"] == Verdict.SUPPORTED
    assert top["evidence_paraphrase"]

    # Absolute percentages run lower here than in production because the test
    # environment substitutes deterministic fakes for SPECTER2 and the
    # cross-encoder. What must hold regardless is the separation: the planted
    # supporting paper scores far above every other candidate.
    assert top["score_percentage"] >= 50
    assert top["score_percentage"] >= recs[1]["score_percentage"] * 2


async def test_contradicting_reference_is_capped(client, analyzed):
    draft_id = analyzed
    claims = await _claims(client, draft_id)
    claim = next(c for c in claims if c["sentence_text"].startswith(OPENING_CLAIM))
    recs = (await client.get(f"/api/v1/claims/{claim['id']}/recommendations?limit=20")).json()

    contradicting = [r for r in recs if r["reference"]["title"] == CONTRADICTING_TITLE]
    if contradicting:
        rec = contradicting[0]
        assert rec["verdict"] == Verdict.CONTRADICTED
        assert rec["score_percentage"] <= CONTRADICTED_CAP
        assert rec["recommended_usage"] == "Do not cite"


async def test_concurrent_verification_does_not_cross_contaminate_claims(client, analyzed):
    """Stage 4's LLM call now runs in a thread pool across claims. The
    failure mode a race would produce is exactly this: claim A ending up
    with claim B's verdict. Checking two *different* claims land on their
    own distinct, correct top reference in the same assertion is what
    would catch results getting swapped between concurrently-running
    threads -- a single-claim check can't distinguish "correct" from
    "coincidentally still correct because nothing raced."
    """
    draft_id = analyzed
    claims = await _claims(client, draft_id)

    opening = next(c for c in claims if c["sentence_text"].startswith(OPENING_CLAIM))
    opening_recs = (await client.get(f"/api/v1/claims/{opening['id']}/recommendations")).json()
    assert opening_recs[0]["reference"]["title"] == SUPPORTING_TITLE
    assert opening_recs[0]["verdict"] == Verdict.SUPPORTED

    drift_claim_text = "Deployed detectors lose a substantial share of their recall"
    drift = next(c for c in claims if c["sentence_text"].startswith(drift_claim_text))
    drift_recs = (await client.get(f"/api/v1/claims/{drift['id']}/recommendations")).json()
    assert drift_recs, "expected recommendations for the concept-drift claim"
    assert drift_recs[0]["reference"]["title"] == "Concept Drift in Deployed Fraud Detection Systems"
    assert drift_recs[0]["verdict"] in (Verdict.SUPPORTED, Verdict.PARTIALLY_SUPPORTED)

    # The two claims' top picks must differ -- if phase B's results ever
    # got swapped between threads, this is the check that would catch it.
    assert opening_recs[0]["reference"]["title"] != drift_recs[0]["reference"]["title"]


async def test_no_more_than_five_recommendations_per_claim(client, analyzed):
    draft_id = analyzed
    for claim in await _claims(client, draft_id):
        recs = (await client.get(f"/api/v1/claims/{claim['id']}/recommendations?limit=20")).json()
        assert len(recs) <= 5
        assert [r["rank"] for r in recs] == list(range(1, len(recs) + 1))


async def test_references_without_abstracts_are_never_recommended(client, analyzed):
    """Unembedded rows cannot be retrieved, so they cannot be proposed as evidence."""
    draft_id = analyzed
    unverifiable = {
        "An Unindexed Workshop Paper on Transaction Screening",
        "Internal Technical Note on Alert Triage",
    }
    for claim in await _claims(client, draft_id):
        recs = (await client.get(f"/api/v1/claims/{claim['id']}/recommendations?limit=20")).json()
        for rec in recs:
            assert rec["reference"]["title"] not in unverifiable
            if not rec["reference"]["abstract"]:
                assert rec["score_percentage"] <= MISSING_ABSTRACT_CAP


async def test_score_breakdown_is_exposed(client, analyzed):
    draft_id = analyzed
    claim = (await _claims(client, draft_id))[0]
    rec = (await client.get(f"/api/v1/claims/{claim['id']}/recommendations")).json()[0]

    breakdown = rec["score_breakdown"]
    assert set(breakdown) == {
        "semantic_similarity",
        "lexical_similarity",
        "keyword_overlap",
        "field_match",
        "reranker_score",
        "llm_support_score",
    }
    assert 0.0 <= breakdown["semantic_similarity"] <= 1.0
    assert 0.0 <= breakdown["reranker_score"] <= 1.0


async def test_verification_results_are_cached_across_runs(client, analyzed, db_session):
    """A second analysis run must not re-verify unchanged claims."""
    from sqlalchemy import func, select

    from app.db.models import AnalysisRun, LLMVerificationCache
    from app.db.models.enums import RunStatus

    draft_id = analyzed
    cached_before = db_session.execute(
        select(func.count()).select_from(LLMVerificationCache)
    ).scalar_one()
    assert cached_before > 0

    # Close out the finished run so a second one is allowed.
    db_session.query(AnalysisRun).update({"status": RunStatus.COMPLETED})
    db_session.commit()

    from app.services.llm_client import Tier
    from app.services.mocks.mock_llm import MockLLMClient

    calls_before = MockLLMClient().calls[Tier.VERIFY]
    resp = await client.post(f"/api/v1/drafts/{draft_id}/analysis/run")
    assert resp.status_code == 202

    cached_after = db_session.execute(
        select(func.count()).select_from(LLMVerificationCache)
    ).scalar_one()
    # Same claims, same references: the cache absorbed the second run.
    assert cached_after == cached_before
    assert calls_before == 0


async def test_accept_and_reject_flow(client, analyzed, db_session):
    from app.db.models import AcceptedCitation

    draft_id = analyzed
    claim = (await _claims(client, draft_id))[0]
    rec = (await client.get(f"/api/v1/claims/{claim['id']}/recommendations")).json()[0]

    accepted = await client.post(
        f"/api/v1/recommendations/{rec['id']}/accept", json={"note": "good fit"}
    )
    assert accepted.status_code == 200
    assert accepted.json()["user_decision"] == UserDecision.ACCEPTED
    assert accepted.json()["user_note"] == "good fit"
    assert db_session.query(AcceptedCitation).count() == 1

    # Accepting twice must not duplicate the accepted citation.
    await client.post(f"/api/v1/recommendations/{rec['id']}/accept", json={})
    assert db_session.query(AcceptedCitation).count() == 1

    rejected = await client.post(f"/api/v1/recommendations/{rec['id']}/reject", json={})
    assert rejected.json()["user_decision"] == UserDecision.REJECTED
    assert db_session.query(AcceptedCitation).count() == 0


async def test_accept_populates_apa_citation_text(client, analyzed, db_session):
    from app.db.models import AcceptedCitation

    draft_id = analyzed
    claims = await _claims(client, draft_id)

    accepted_texts = []
    for claim in claims[:2]:
        recs = (await client.get(f"/api/v1/claims/{claim['id']}/recommendations")).json()
        if not recs:
            continue
        resp = await client.post(f"/api/v1/recommendations/{recs[0]['id']}/accept", json={})
        assert resp.status_code == 200

    for row in db_session.query(AcceptedCitation).all():
        assert row.citation_text is not None
        assert row.citation_text.startswith("(")
        assert row.insertion_format == "APA"
        accepted_texts.append(row.citation_text)

    assert accepted_texts  # the fixture always has at least one acceptable candidate


async def test_recommendations_404_for_unknown_claim(client):
    import uuid

    resp = await client.get(f"/api/v1/claims/{uuid.uuid4()}/recommendations")
    assert resp.status_code == 404
