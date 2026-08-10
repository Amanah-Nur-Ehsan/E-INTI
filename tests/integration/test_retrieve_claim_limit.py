"""retrieve_claim_limit caps which claims enter retrieval (stages 1-3),
picked by Claim.claim_confidence -- the single largest CPU saving in the
pipeline, since retrieval used to run over every citation-worthy claim and
discard most of that work after the fact.
"""

import pytest
from sqlalchemy import delete, select

from app.db.models import CitationRecommendation, Claim
from app.services.recommendation_pipeline import recommend_for_draft

pytestmark = pytest.mark.integration


async def _detect_claims_and_clear_recommendations(client, db_session, draft_id):
    """Run the full chain (CELERY_TASK_ALWAYS_EAGER makes analysis/run
    synchronous, so recommend_for_draft already ran once with the default,
    uncapped settings by the time this returns) to get real detected claims,
    then wipe its recommendations so this test's own recommend_for_draft
    call starts from a clean slate instead of comparing against leftovers.
    """
    resp = await client.post(f"/api/v1/drafts/{draft_id}/analysis/run")
    assert resp.status_code == 202, resp.text
    status = (await client.get(f"/api/v1/drafts/{draft_id}/analysis/status")).json()
    assert status["status"] == "COMPLETED", status

    claim_ids = db_session.execute(
        select(Claim.id).where(Claim.draft_id == draft_id, Claim.needs_citation.is_(True))
    ).scalars()
    db_session.execute(
        delete(CitationRecommendation).where(CitationRecommendation.claim_id.in_(claim_ids))
    )
    db_session.commit()
    return status


async def test_retrieve_claim_limit_keeps_only_the_highest_confidence_claims(
    client, db_session, seeded_draft, monkeypatch, settings
):
    draft_id = seeded_draft
    await _detect_claims_and_clear_recommendations(client, db_session, draft_id)

    claims = list(
        db_session.execute(
            select(Claim).where(Claim.draft_id == draft_id, Claim.needs_citation.is_(True))
        ).scalars()
    )
    assert len(claims) >= 2, "fixture needs at least 2 citation-worthy claims for this test"

    # Force a clear, known ranking: everyone else low, one claim highest.
    for claim in claims:
        claim.claim_confidence = 0.1
    winner = claims[0]
    winner.claim_confidence = 0.99
    db_session.commit()

    monkeypatch.setattr(settings, "retrieve_claim_limit", 1)
    result = recommend_for_draft(db_session, draft_id)

    assert result["claims_processed"] == 1

    recommended_claim_ids = set(
        db_session.execute(select(CitationRecommendation.claim_id).distinct()).scalars()
    )
    assert recommended_claim_ids <= {winner.id}
    for claim in claims:
        if claim.id != winner.id:
            assert claim.id not in recommended_claim_ids


async def test_retrieve_claim_limit_zero_means_no_cap(
    client, db_session, seeded_draft, monkeypatch, settings
):
    draft_id = seeded_draft
    await _detect_claims_and_clear_recommendations(client, db_session, draft_id)

    claims = list(
        db_session.execute(
            select(Claim).where(Claim.draft_id == draft_id, Claim.needs_citation.is_(True))
        ).scalars()
    )

    monkeypatch.setattr(settings, "retrieve_claim_limit", 0)
    result = recommend_for_draft(db_session, draft_id)

    assert result["claims_processed"] == len(claims)
