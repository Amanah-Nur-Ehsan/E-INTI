import pytest

from app.db.models.enums import RunStage, RunStatus
from tests.conftest import import_dataset, upload_draft

pytestmark = pytest.mark.integration


async def test_run_requires_references(client):
    draft_id = await upload_draft(client)
    resp = await client.post(f"/api/v1/drafts/{draft_id}/analysis/run")
    assert resp.status_code == 400
    assert "library" in resp.json()["detail"]


async def test_run_404s_for_unknown_draft(client):
    import uuid

    resp = await client.post(f"/api/v1/drafts/{uuid.uuid4()}/analysis/run")
    assert resp.status_code == 404


async def test_chain_runs_all_stages_to_completion(client, seeded_draft):
    resp = await client.post(f"/api/v1/drafts/{seeded_draft}/analysis/run")
    assert resp.status_code == 202

    body = (await client.get(f"/api/v1/drafts/{seeded_draft}/analysis/status")).json()
    # Eager mode runs the whole chain inline before the POST returns.
    assert body["status"] == RunStatus.COMPLETED
    assert body["stage"] == RunStage.RECOMMENDING
    assert body["error"] is None
    assert body["references"]["total"] == 12
    assert body["references"]["pending"] == 0
    assert body["references"]["embedded"] == 10


async def test_second_run_is_rejected_while_one_is_active(client, seeded_draft, db_session):
    from app.db.models import AnalysisRun

    await client.post(f"/api/v1/drafts/{seeded_draft}/analysis/run")
    # Simulate a still-running job: eager mode would otherwise finish instantly.
    run = db_session.query(AnalysisRun).one()
    run.status = RunStatus.RUNNING
    db_session.commit()

    resp = await client.post(f"/api/v1/drafts/{seeded_draft}/analysis/run")
    assert resp.status_code == 409
    assert "already in progress" in resp.json()["detail"]


async def test_references_status_endpoint(client):
    await upload_draft(client)
    await import_dataset(client)
    body = (await client.get("/api/v1/library/status")).json()
    assert body == {
        "total": 12,
        "pending": 5,
        "enriched": 7,
        "incomplete": 0,
        "failed": 0,
        "embedded": 0,
        "missing_abstract": 5,
        "embed_pending": 7,
    }
