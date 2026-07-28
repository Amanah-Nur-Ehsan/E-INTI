import pytest

from app.db.models import Draft, ReferencePaper
from app.db.models.enums import RunStage, RunStatus

pytestmark = pytest.mark.integration


async def _project_with_inputs(client, db_session):
    """Create a project plus one draft row and one reference row."""
    project_id = (await client.post("/api/v1/projects", json={"name": "P"})).json()["id"]
    db_session.add(
        Draft(
            project_id=project_id,
            original_filename="d.docx",
            storage_path="/tmp/d.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    )
    db_session.add(ReferencePaper(project_id=project_id, title="A paper", original_data={}))
    db_session.commit()
    return project_id


async def test_run_requires_draft_and_references(client):
    project_id = (await client.post("/api/v1/projects", json={"name": "Empty"})).json()["id"]
    resp = await client.post(f"/api/v1/projects/{project_id}/analysis/run", json={})
    assert resp.status_code == 400
    assert "draft" in resp.json()["detail"]


async def test_chain_runs_all_stages_to_completion(client, db_session):
    project_id = await _project_with_inputs(client, db_session)

    resp = await client.post(f"/api/v1/projects/{project_id}/analysis/run", json={})
    assert resp.status_code == 202

    status_resp = await client.get(f"/api/v1/projects/{project_id}/analysis/status")
    body = status_resp.json()
    # Eager mode runs the whole chain inline before the POST returns.
    assert body["status"] == RunStatus.COMPLETED
    assert body["stage"] == RunStage.RECOMMENDING
    assert body["error"] is None
    assert body["references"]["total"] == 1
    assert body["references"]["pending"] == 1
    assert body["claims"]["total"] == 0


async def test_references_status_endpoint(client, db_session):
    project_id = await _project_with_inputs(client, db_session)
    body = (await client.get(f"/api/v1/projects/{project_id}/references/status")).json()
    assert body == {
        "total": 1,
        "pending": 1,
        "enriched": 0,
        "incomplete": 0,
        "failed": 0,
        "embedded": 0,
    }
