import pytest

from app.db.models.enums import RunStage, RunStatus
from tests.conftest import create_project, import_dataset, upload_draft

pytestmark = pytest.mark.integration


async def test_run_requires_a_draft(client):
    project_id = await create_project(client, "Empty")
    resp = await client.post(f"/api/v1/projects/{project_id}/analysis/run", json={})
    assert resp.status_code == 400
    assert "draft" in resp.json()["detail"]


async def test_run_requires_references(client):
    project_id = await create_project(client, "Draft only")
    await upload_draft(client, project_id)
    resp = await client.post(f"/api/v1/projects/{project_id}/analysis/run", json={})
    assert resp.status_code == 400
    assert "references" in resp.json()["detail"]


async def test_chain_runs_all_stages_to_completion(client, seeded_project):
    resp = await client.post(f"/api/v1/projects/{seeded_project}/analysis/run", json={})
    assert resp.status_code == 202

    body = (await client.get(f"/api/v1/projects/{seeded_project}/analysis/status")).json()
    # Eager mode runs the whole chain inline before the POST returns.
    assert body["status"] == RunStatus.COMPLETED
    assert body["stage"] == RunStage.RECOMMENDING
    assert body["error"] is None
    assert body["references"]["total"] == 12
    assert body["references"]["pending"] == 0
    assert body["references"]["embedded"] == 10


async def test_second_run_is_rejected_while_one_is_active(client, seeded_project, db_session):
    from app.db.models import AnalysisRun

    await client.post(f"/api/v1/projects/{seeded_project}/analysis/run", json={})
    # Simulate a still-running job: eager mode would otherwise finish instantly.
    run = db_session.query(AnalysisRun).one()
    run.status = RunStatus.RUNNING
    db_session.commit()

    resp = await client.post(f"/api/v1/projects/{seeded_project}/analysis/run", json={})
    assert resp.status_code == 409
    assert "already in progress" in resp.json()["detail"]


async def test_references_status_endpoint(client):
    project_id = await create_project(client)
    await import_dataset(client, project_id)
    body = (await client.get(f"/api/v1/projects/{project_id}/references/status")).json()
    assert body == {
        "total": 12,
        "pending": 5,
        "enriched": 7,
        "incomplete": 0,
        "failed": 0,
        "embedded": 0,
    }
