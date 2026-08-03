"""GET /drafts/{draft_id}/best-reference: the single reference this paper
should cite, not a list per claim.

The threshold behavior is the whole point of this endpoint: a weak library
match must still come back (flagged), never a 404 or an empty body, because
an empty response reads as "the app is broken" rather than "no strong
match exists yet."
"""

import pytest

pytestmark = pytest.mark.integration


async def _analyzed_draft(client, db_session, seeded_draft):
    draft_id = seeded_draft
    resp = await client.post(f"/api/v1/drafts/{draft_id}/analysis/run")
    assert resp.status_code == 202
    return draft_id


async def test_returns_the_single_highest_scoring_claim_across_the_draft(
    client, db_session, seeded_draft
):
    draft_id = await _analyzed_draft(client, db_session, seeded_draft)

    resp = await client.get(f"/api/v1/drafts/{draft_id}/best-reference")
    assert resp.status_code == 200
    body = resp.json()

    assert body["claim"]["sentence_text"]
    assert body["reference"]["title"]
    assert body["recommendation"]["score_percentage"] == body["recommendation"]["score_percentage"]

    # It must actually be the max across every claim's top pick, not an
    # arbitrary one.
    all_recs = (await client.get(f"/api/v1/drafts/{draft_id}/recommendations")).json()
    top_scores = [recs[0]["score_percentage"] for recs in all_recs.values() if recs]
    assert body["recommendation"]["score_percentage"] == max(top_scores)


async def test_reference_detail_has_the_richer_fields(client, db_session, seeded_draft):
    draft_id = await _analyzed_draft(client, db_session, seeded_draft)
    body = (await client.get(f"/api/v1/drafts/{draft_id}/best-reference")).json()

    # Fields ReferenceSummary doesn't have -- prove the detail schema, not
    # the summary one, is actually what's on the wire.
    for field in ("source_link", "citation_count", "document_type", "field_of_study"):
        assert field in body["reference"]


async def test_threshold_flags_reflect_configured_cutoffs(client, db_session, seeded_draft, monkeypatch):
    from app.core.config import get_settings

    draft_id = await _analyzed_draft(client, db_session, seeded_draft)
    body = (await client.get(f"/api/v1/drafts/{draft_id}/best-reference")).json()
    score = body["recommendation"]["score_percentage"]

    assert body["min_score_threshold"] == get_settings().best_reference_min_score
    assert body["recommended_score_threshold"] == get_settings().best_reference_recommended_score
    assert body["meets_threshold"] == (score >= body["min_score_threshold"])
    assert body["is_recommended"] == (score >= body["recommended_score_threshold"])


async def test_weak_match_is_still_returned_not_hidden(client, db_session, seeded_draft, monkeypatch):
    """Set the threshold above every real score in the fixture library --
    the endpoint must still return the closest match, flagged, not a 404
    or an empty body.
    """
    from app.core import config as config_module

    draft_id = await _analyzed_draft(client, db_session, seeded_draft)

    settings = config_module.get_settings()
    monkeypatch.setattr(settings, "best_reference_min_score", 99.9)
    monkeypatch.setattr(settings, "best_reference_recommended_score", 99.99)

    resp = await client.get(f"/api/v1/drafts/{draft_id}/best-reference")
    assert resp.status_code == 200
    body = resp.json()
    assert body["meets_threshold"] is False
    assert body["is_recommended"] is False
    assert body["reference"]["title"]  # still a real reference, not blank


async def test_404_when_the_draft_has_no_recommendations_at_all(client, db_session, seeded_draft):
    """Before analysis has run, there is nothing to pick a best reference
    from yet -- distinct from a weak match, which is still a real result.
    """
    resp = await client.get(f"/api/v1/drafts/{seeded_draft}/best-reference")
    assert resp.status_code == 404
