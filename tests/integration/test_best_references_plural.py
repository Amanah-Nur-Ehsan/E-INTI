"""GET /drafts/{draft_id}/best-references: the ranked shortlist version of
/best-reference -- up to N references for the whole paper instead of one.
"""

import pytest

pytestmark = pytest.mark.integration


async def _analyzed_draft(client, seeded_draft):
    draft_id = seeded_draft
    resp = await client.post(f"/api/v1/drafts/{draft_id}/analysis/run")
    assert resp.status_code == 202
    return draft_id


async def test_returns_at_most_limit_ordered_by_score(client, db_session, seeded_draft):
    draft_id = await _analyzed_draft(client, seeded_draft)

    resp = await client.get(f"/api/v1/drafts/{draft_id}/best-references?limit=2")
    assert resp.status_code == 200
    body = resp.json()

    assert 0 < len(body) <= 2
    scores = [item["recommendation"]["score_percentage"] for item in body]
    assert scores == sorted(scores, reverse=True)


async def test_default_limit_is_five(client, db_session, seeded_draft):
    draft_id = await _analyzed_draft(client, seeded_draft)
    body = (await client.get(f"/api/v1/drafts/{draft_id}/best-references")).json()
    assert len(body) <= 5


async def test_each_item_carries_its_own_claim_and_matches_the_singular_endpoint(
    client, db_session, seeded_draft
):
    draft_id = await _analyzed_draft(client, seeded_draft)

    plural = (await client.get(f"/api/v1/drafts/{draft_id}/best-references")).json()
    singular = (await client.get(f"/api/v1/drafts/{draft_id}/best-reference")).json()

    assert plural, "expected at least one reference"
    for item in plural:
        assert item["claim"]["sentence_text"]
        assert item["reference"]["title"]

    # #1 in the shortlist must be exactly what the singular endpoint picks.
    assert plural[0]["reference"]["title"] == singular["reference"]["title"]
    assert plural[0]["recommendation"]["score_percentage"] == singular["recommendation"]["score_percentage"]


async def test_the_same_reference_never_appears_twice(client, db_session, seeded_draft):
    """A reference that's the strongest match for more than one claim must
    only take one slot in the shortlist -- otherwise one dominant reference
    could fill the entire list with itself.
    """
    draft_id = await _analyzed_draft(client, seeded_draft)
    body = (await client.get(f"/api/v1/drafts/{draft_id}/best-references?limit=20")).json()

    reference_ids = [item["reference"]["id"] for item in body]
    assert len(reference_ids) == len(set(reference_ids))


async def test_empty_list_not_404_when_the_draft_has_no_recommendations_yet(
    client, db_session, seeded_draft
):
    """Unlike /best-reference (which 404s only when truly nothing exists,
    since it always returns *a* pick), a list endpoint's natural "nothing
    yet" state is an empty list, not an error.
    """
    resp = await client.get(f"/api/v1/drafts/{seeded_draft}/best-references")
    assert resp.status_code == 200
    assert resp.json() == []
