"""POST /recommendations/{id}/rewrite-paragraph: weaves a chosen
reference's citation into the claim's paragraph, in the requested style.

The citation string itself is never left to the model -- it's computed
deterministically by citation_formatting_service first, so these tests
assert the *real* in-text/bibliography formatting shows up in the
result, not just that some text came back.
"""

import pytest

pytestmark = pytest.mark.integration


async def _analyzed_draft_first_recommendation(client, seeded_draft):
    draft_id = seeded_draft
    await client.post(f"/api/v1/drafts/{draft_id}/analysis/run")
    claims = (await client.get(f"/api/v1/drafts/{draft_id}/claims?needs_citation=true")).json()
    for claim in claims:
        recs = (await client.get(f"/api/v1/claims/{claim['id']}/recommendations")).json()
        if recs:
            return recs[0]["id"], claim
    raise AssertionError("fixture produced no recommendations to rewrite against")


async def test_rewrite_weaves_in_the_real_apa_citation(client, db_session, seeded_draft):
    rec_id, claim = await _analyzed_draft_first_recommendation(client, seeded_draft)

    resp = await client.post(
        f"/api/v1/recommendations/{rec_id}/rewrite-paragraph", json={"style": "APA"}
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["style"] == "APA"
    assert body["in_text_citation"].startswith("(")
    assert body["in_text_citation"] in body["paragraph"]
    assert body["bibliography_entry"]


async def test_rewrite_respects_ieee_style(client, db_session, seeded_draft):
    rec_id, _claim = await _analyzed_draft_first_recommendation(client, seeded_draft)

    resp = await client.post(
        f"/api/v1/recommendations/{rec_id}/rewrite-paragraph", json={"style": "IEEE"}
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["style"] == "IEEE"
    assert body["in_text_citation"] == "[1]"
    assert "[1]" in body["paragraph"]
    assert body["bibliography_entry"].startswith("[1]")


async def test_rewrite_defaults_to_apa_when_style_omitted(client, db_session, seeded_draft):
    rec_id, _claim = await _analyzed_draft_first_recommendation(client, seeded_draft)

    resp = await client.post(f"/api/v1/recommendations/{rec_id}/rewrite-paragraph", json={})
    assert resp.status_code == 200
    assert resp.json()["style"] == "APA"


async def test_rewrite_rejects_an_unsupported_style(client, db_session, seeded_draft):
    rec_id, _claim = await _analyzed_draft_first_recommendation(client, seeded_draft)

    resp = await client.post(
        f"/api/v1/recommendations/{rec_id}/rewrite-paragraph", json={"style": "MLA"}
    )
    assert resp.status_code == 422


async def test_rewrite_404s_for_unknown_recommendation(client, db_session):
    import uuid

    resp = await client.post(
        f"/api/v1/recommendations/{uuid.uuid4()}/rewrite-paragraph", json={"style": "APA"}
    )
    assert resp.status_code == 404
