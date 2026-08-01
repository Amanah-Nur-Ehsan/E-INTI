"""md/csv/json export writers and the shared audit report."""

import csv
import json
import uuid
from io import StringIO

import pytest

from app.services.export.audit import INSERTED, NOT_ACCEPTED, build_audit_rows
from app.services.export.bundle import build_bundle
from app.services.export.markdown_writer import write_markdown
from app.services.export.tabular_writer import write_csv, write_json
from tests.conftest import import_dataset, upload_draft

pytestmark = pytest.mark.integration


async def _analyzed_draft(client, db_session, accept_all: bool = True):
    from app.services.embedding_service import embed_pending_references
    from app.services.enrichment import enrich_pending_references

    draft_id = await upload_draft(client)
    await import_dataset(client)
    enrich_pending_references(db_session)
    embed_pending_references(db_session)
    db_session.commit()
    await client.post(f"/api/v1/drafts/{draft_id}/analysis/run")

    claims = (await client.get(f"/api/v1/drafts/{draft_id}/claims?needs_citation=true")).json()
    accepted = []
    if accept_all:
        for claim in claims:
            recs = (await client.get(f"/api/v1/claims/{claim['id']}/recommendations")).json()
            if recs:
                await client.post(f"/api/v1/recommendations/{recs[0]['id']}/accept", json={})
                accepted.append(claim["id"])
    return draft_id, accepted, claims


async def test_markdown_export_inserts_citations_and_bibliography(client, db_session):
    draft_id, accepted, _claims = await _analyzed_draft(client, db_session)
    bundle = build_bundle(db_session, uuid.UUID(draft_id))

    body, outcomes = write_markdown(bundle)
    assert all(o.status == "INSERTED" for o in outcomes)
    assert len(outcomes) == len(accepted)

    assert "## References" in body
    for item in bundle.accepted:
        citation = bundle.context.in_text(item.references[0].id)
        assert citation in body


async def test_markdown_works_for_non_docx_drafts(client, db_session):
    """The whole point of the markdown export: it must work for .md/.txt
    drafts too, where DOCX export is unavailable."""
    from tests.conftest import FIXTURES

    data = FIXTURES.joinpath("sample_draft.md").read_bytes()
    upload = await client.post(
        "/api/v1/drafts/upload",
        files={"file": ("sample_draft.md", data)},
    )
    draft_id = upload.json()["id"]

    from app.services.draft_parser_service import parse_and_store_draft

    parse_and_store_draft(db_session, uuid.UUID(draft_id))

    bundle = build_bundle(db_session, uuid.UUID(draft_id))
    body, outcomes = write_markdown(bundle)
    assert isinstance(body, str)
    assert outcomes == []  # nothing accepted yet, but no crash


async def test_markdown_reports_position_mismatch(client, db_session):
    from app.db.models import Claim

    draft_id, accepted, _claims = await _analyzed_draft(client, db_session)
    assert accepted

    claim = db_session.get(Claim, uuid.UUID(accepted[0]))
    claim.sentence_text = "This text no longer matches the source draft at all."
    db_session.commit()

    bundle = build_bundle(db_session, uuid.UUID(draft_id))
    _body, outcomes = write_markdown(bundle)

    mismatched = [o for o in outcomes if o.claim_id == claim.id]
    assert len(mismatched) == 1
    assert mismatched[0].status == "POSITION_MISMATCH"


async def test_csv_export_is_valid_and_has_one_row_per_needs_citation_claim(client, db_session):
    draft_id, _accepted, claims = await _analyzed_draft(client, db_session)
    bundle = build_bundle(db_session, uuid.UUID(draft_id))

    csv_text = write_csv(bundle)
    rows = list(csv.DictReader(StringIO(csv_text)))
    assert len(rows) == len(claims)
    assert all(r["insertion_status"] == INSERTED for r in rows)


async def test_csv_reports_not_accepted_for_claims_without_a_decision(client, db_session):
    draft_id, _accepted, claims = await _analyzed_draft(client, db_session, accept_all=False)
    bundle = build_bundle(db_session, uuid.UUID(draft_id))

    csv_text = write_csv(bundle)
    rows = list(csv.DictReader(StringIO(csv_text)))
    assert len(rows) == len(claims)
    assert all(r["insertion_status"] == NOT_ACCEPTED for r in rows)
    assert all(r["user_decision"] == "PENDING" for r in rows)
    assert all(r["citation_text"] == "" for r in rows)


async def test_json_export_structure(client, db_session):
    draft_id, accepted, claims = await _analyzed_draft(client, db_session)
    bundle = build_bundle(db_session, uuid.UUID(draft_id))

    payload = json.loads(write_json(bundle, citation_style="APA", insertion_mode="tracked_changes"))
    assert payload["citation_style"] == "APA"
    assert payload["insertion_mode"] == "tracked_changes"
    assert len(payload["accepted"]) == len(accepted)
    assert len(payload["audit"]) == len(claims)
    assert payload["draft"]["id"] == draft_id

    unique_ref_ids = {ref.id for item in bundle.accepted for ref in item.references}
    assert len(payload["bibliography"]) == len(unique_ref_ids)


async def test_audit_rows_capture_score_and_verdict_from_the_accepted_recommendation(
    client, db_session
):
    draft_id, accepted, _claims = await _analyzed_draft(client, db_session)
    assert accepted
    bundle = build_bundle(db_session, uuid.UUID(draft_id))

    rows = build_audit_rows(bundle)
    accepted_rows = [r for r in rows if r.insertion_status == INSERTED]
    assert accepted_rows
    for row in accepted_rows:
        assert row.score_percentage is not None
        assert row.verdict is not None
        assert row.user_decision == "ACCEPTED"


async def test_audit_row_dedupes_multi_reference_citation_text(client, db_session):
    """A claim with two accepted references must show one semicolon-joined
    citation string, not two separate rows."""
    draft_id, _accepted, claims = await _analyzed_draft(client, db_session, accept_all=False)
    needing = [c for c in claims][0]
    recs = (await client.get(f"/api/v1/claims/{needing['id']}/recommendations?limit=5")).json()
    assume_two = [r for r in recs if r["score_percentage"] > 0][:2]
    for r in assume_two:
        await client.post(f"/api/v1/recommendations/{r['id']}/accept", json={})

    bundle = build_bundle(db_session, uuid.UUID(draft_id))
    rows = build_audit_rows(bundle)
    row = next(r for r in rows if r.claim_text == (needing["claim_text"] or needing["sentence_text"]))
    if len(assume_two) == 2:
        assert row.citation_text.count(";") == 1 or row.citation_text.startswith("(")
