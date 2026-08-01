"""POST /projects/{id}/exports and the download endpoint, across all
four formats, through the real HTTP layer.
"""

import pytest
from docx import Document

from tests.conftest import create_project, import_dataset, upload_draft

pytestmark = pytest.mark.integration


async def _analyzed_project(client, db_session):
    from app.services.embedding_service import embed_pending_references
    from app.services.enrichment import enrich_pending_references

    project_id = await create_project(client, "P", field_of_study="Computer Science")
    await upload_draft(client, project_id)
    await import_dataset(client, project_id)
    enrich_pending_references(db_session)
    embed_pending_references(db_session)
    db_session.commit()
    await client.post(f"/api/v1/projects/{project_id}/analysis/run", json={})

    status = (await client.get(f"/api/v1/projects/{project_id}/analysis/status")).json()
    draft_id = status["draft_id"]
    claims = (await client.get(f"/api/v1/drafts/{draft_id}/claims?needs_citation=true")).json()
    for claim in claims:
        recs = (await client.get(f"/api/v1/claims/{claim['id']}/recommendations")).json()
        if recs:
            await client.post(f"/api/v1/recommendations/{recs[0]['id']}/accept", json={})
    return project_id, draft_id


@pytest.mark.parametrize("fmt", ["docx", "md", "csv", "json"])
async def test_export_and_download_round_trip(client, db_session, fmt):
    project_id, _draft_id = await _analyzed_project(client, db_session)

    resp = await client.post(f"/api/v1/projects/{project_id}/exports", json={"format": fmt})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["format"] == fmt
    assert body["byte_size"] > 0
    assert body["filename"].endswith(f".{fmt}")

    download = await client.get(f"/api/v1/exports/{body['id']}/download")
    assert download.status_code == 200
    assert len(download.content) == body["byte_size"]


async def test_docx_export_reports_inserted_count(client, db_session):
    project_id, _draft_id = await _analyzed_project(client, db_session)
    resp = await client.post(f"/api/v1/projects/{project_id}/exports", json={"format": "docx"})
    body = resp.json()
    assert body["inserted_count"] > 0
    assert body["mismatch_count"] == 0
    assert len(body["outcomes"]) == body["inserted_count"] + body["mismatch_count"]


async def test_docx_export_includes_audit_table_when_requested(client, db_session, tmp_path):
    project_id, _draft_id = await _analyzed_project(client, db_session)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/exports",
        json={"format": "docx", "include_audit_report": True},
    )
    export_id = resp.json()["id"]
    download = await client.get(f"/api/v1/exports/{export_id}/download")

    out = tmp_path / "export.docx"
    out.write_bytes(download.content)
    doc = Document(str(out))
    assert len(doc.tables) == 1
    assert [c.text for c in doc.tables[0].rows[0].cells][0] == "Section"


async def test_docx_export_excludes_audit_table_when_not_requested(client, db_session, tmp_path):
    project_id, _draft_id = await _analyzed_project(client, db_session)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/exports",
        json={"format": "docx", "include_audit_report": False},
    )
    export_id = resp.json()["id"]
    download = await client.get(f"/api/v1/exports/{export_id}/download")

    out = tmp_path / "export.docx"
    out.write_bytes(download.content)
    doc = Document(str(out))
    assert len(doc.tables) == 0


async def test_export_defaults_to_latest_draft_when_unspecified(client, db_session):
    project_id, draft_id = await _analyzed_project(client, db_session)
    resp = await client.post(f"/api/v1/projects/{project_id}/exports", json={"format": "json"})
    assert resp.status_code == 201
    assert resp.json()["draft_id"] == draft_id


async def test_export_with_no_draft_returns_422(client, db_session):
    project_id = await create_project(client, "Empty")
    resp = await client.post(f"/api/v1/projects/{project_id}/exports", json={"format": "json"})
    assert resp.status_code == 422


async def test_list_exports_ordered_newest_first(client, db_session):
    project_id, _draft_id = await _analyzed_project(client, db_session)
    first = await client.post(f"/api/v1/projects/{project_id}/exports", json={"format": "csv"})
    second = await client.post(f"/api/v1/projects/{project_id}/exports", json={"format": "json"})

    listing = (await client.get(f"/api/v1/projects/{project_id}/exports")).json()
    assert len(listing) == 2
    assert listing[0]["id"] == second.json()["id"]
    assert listing[1]["id"] == first.json()["id"]


async def test_download_unknown_export_404s(client, db_session):
    import uuid

    resp = await client.get(f"/api/v1/exports/{uuid.uuid4()}/download")
    assert resp.status_code == 404


async def test_insertion_mode_direct_produces_no_tracked_changes(client, db_session, tmp_path):
    project_id, _draft_id = await _analyzed_project(client, db_session)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/exports",
        json={"format": "docx", "insertion_mode": "direct"},
    )
    export_id = resp.json()["id"]
    download = await client.get(f"/api/v1/exports/{export_id}/download")

    out = tmp_path / "export.docx"
    out.write_bytes(download.content)
    doc = Document(str(out))
    assert len(doc.element.body.xpath(".//w:ins")) == 0
