"""The batch/decision/summary endpoints added specifically for the review
UI's data needs.
"""

import pytest

from app.db.models.enums import UserDecision
from tests.conftest import import_dataset, upload_draft

pytestmark = pytest.mark.integration


async def _analyzed_draft(client, db_session) -> str:
    from app.services.embedding_service import embed_pending_references
    from app.services.enrichment import enrich_pending_references

    draft_id = await upload_draft(client)
    await import_dataset(client)
    enrich_pending_references(db_session)
    embed_pending_references(db_session)
    db_session.commit()
    await client.post(f"/api/v1/drafts/{draft_id}/analysis/run")
    return draft_id


async def test_batch_recommendations_covers_every_needs_citation_claim(client, db_session):
    draft_id = await _analyzed_draft(client, db_session)
    claims = (await client.get(f"/api/v1/drafts/{draft_id}/claims?needs_citation=true")).json()

    batch = (await client.get(f"/api/v1/drafts/{draft_id}/recommendations")).json()
    for claim in claims:
        assert claim["id"] in batch
        assert len(batch[claim["id"]]) <= 5


async def test_batch_recommendations_respects_limit_per_claim(client, db_session):
    draft_id = await _analyzed_draft(client, db_session)
    batch = (
        await client.get(f"/api/v1/drafts/{draft_id}/recommendations?limit_per_claim=2")
    ).json()
    assert all(len(recs) <= 2 for recs in batch.values())


async def test_decision_endpoint_accepts(client, db_session):
    draft_id = await _analyzed_draft(client, db_session)
    claims = (await client.get(f"/api/v1/drafts/{draft_id}/claims?needs_citation=true")).json()
    recs = (await client.get(f"/api/v1/claims/{claims[0]['id']}/recommendations")).json()

    resp = await client.post(
        f"/api/v1/recommendations/{recs[0]['id']}/decision",
        json={"decision": "ACCEPTED", "note": "good"},
    )
    assert resp.status_code == 200
    assert resp.json()["user_decision"] == UserDecision.ACCEPTED
    assert resp.json()["user_note"] == "good"


async def test_decision_endpoint_marks_irrelevant(client, db_session):
    draft_id = await _analyzed_draft(client, db_session)
    claims = (await client.get(f"/api/v1/drafts/{draft_id}/claims?needs_citation=true")).json()
    recs = (await client.get(f"/api/v1/claims/{claims[0]['id']}/recommendations")).json()

    resp = await client.post(
        f"/api/v1/recommendations/{recs[0]['id']}/decision", json={"decision": "IRRELEVANT"}
    )
    assert resp.status_code == 200
    assert resp.json()["user_decision"] == "IRRELEVANT"


async def test_decision_endpoint_rejects_invalid_value(client, db_session):
    draft_id = await _analyzed_draft(client, db_session)
    claims = (await client.get(f"/api/v1/drafts/{draft_id}/claims?needs_citation=true")).json()
    recs = (await client.get(f"/api/v1/claims/{claims[0]['id']}/recommendations")).json()

    resp = await client.post(
        f"/api/v1/recommendations/{recs[0]['id']}/decision", json={"decision": "MAYBE"}
    )
    assert resp.status_code == 422


async def test_irrelevant_removes_a_prior_acceptance(client, db_session):
    draft_id = await _analyzed_draft(client, db_session)
    claims = (await client.get(f"/api/v1/drafts/{draft_id}/claims?needs_citation=true")).json()
    recs = (await client.get(f"/api/v1/claims/{claims[0]['id']}/recommendations")).json()
    rec_id = recs[0]["id"]

    await client.post(f"/api/v1/recommendations/{rec_id}/decision", json={"decision": "ACCEPTED"})
    accepted = (await client.get(f"/api/v1/drafts/{draft_id}/accepted-citations")).json()
    assert claims[0]["id"] in accepted

    await client.post(f"/api/v1/recommendations/{rec_id}/decision", json={"decision": "IRRELEVANT"})
    accepted_after = (await client.get(f"/api/v1/drafts/{draft_id}/accepted-citations")).json()
    assert claims[0]["id"] not in accepted_after


async def test_accepted_citations_endpoint_returns_joined_text(client, db_session):
    draft_id = await _analyzed_draft(client, db_session)
    claims = (await client.get(f"/api/v1/drafts/{draft_id}/claims?needs_citation=true")).json()

    accepted_claim_ids = []
    for claim in claims[:2]:
        recs = (await client.get(f"/api/v1/claims/{claim['id']}/recommendations")).json()
        if recs:
            await client.post(f"/api/v1/recommendations/{recs[0]['id']}/accept", json={})
            accepted_claim_ids.append(claim["id"])

    ghost_text = (await client.get(f"/api/v1/drafts/{draft_id}/accepted-citations")).json()
    for claim_id in accepted_claim_ids:
        assert claim_id in ghost_text
        assert ghost_text[claim_id].startswith("(")


async def test_draft_summary_before_analysis(client, db_session):
    draft_id = await upload_draft(client)
    summary = (await client.get(f"/api/v1/drafts/{draft_id}/summary")).json()
    assert summary["draft_id"] == draft_id
    assert summary["claims"]["total"] == 0
    assert summary["coverage_percentage"] == 0.0
    assert summary["latest_run"] is None


async def test_draft_summary_reflects_analysis_and_acceptance(client, db_session):
    draft_id = await _analyzed_draft(client, db_session)
    claims = (await client.get(f"/api/v1/drafts/{draft_id}/claims?needs_citation=true")).json()

    for claim in claims:
        recs = (await client.get(f"/api/v1/claims/{claim['id']}/recommendations")).json()
        if recs:
            await client.post(f"/api/v1/recommendations/{recs[0]['id']}/accept", json={})

    summary = (await client.get(f"/api/v1/drafts/{draft_id}/summary")).json()
    assert summary["draft_id"] == draft_id
    assert summary["references"]["total"] == 12
    assert summary["claims"]["needs_citation"] == len(claims)
    assert summary["claims_with_accepted"] > 0
    assert summary["latest_run"]["status"] == "COMPLETED"
    assert 0 < summary["coverage_percentage"] <= 100

    expected = round(100 * summary["claims_with_accepted"] / summary["claims"]["needs_citation"], 1)
    assert summary["coverage_percentage"] == expected
