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


async def test_completed_run_stores_result_snapshot(client, seeded_draft, db_session):
    from app.db.models import AnalysisRun

    await client.post(f"/api/v1/drafts/{seeded_draft}/analysis/run")
    run = db_session.query(AnalysisRun).one()
    assert run.result_json is not None
    assert run.result_json["draft"]["filename"]
    assert "sdg" in run.result_json
    assert isinstance(run.result_json["claims"], list)
    assert run.result_json["summary"]["claims_total"] >= 0


async def test_history_lists_and_returns_detail(client, seeded_draft):
    await client.post(f"/api/v1/drafts/{seeded_draft}/analysis/run")

    list_resp = await client.get("/api/v1/analysis/history")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) >= 1
    item = items[0]
    assert item["status"] == RunStatus.COMPLETED
    assert item["filename"]

    detail_resp = await client.get(f"/api/v1/analysis/history/{item['run_id']}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["run"]["id"] == item["run_id"]
    assert "raw_text" in detail["draft"]
    assert isinstance(detail["claims"], list)


async def test_history_requires_login(anon_client):
    resp = await anon_client.get("/api/v1/analysis/history")
    assert resp.status_code == 401


async def test_history_is_scoped_per_user(
    client, seeded_draft, email_stub, settings, monkeypatch
):
    import re

    import httpx

    from app.main import app

    monkeypatch.setattr(settings, "registration_enabled", True)
    await client.post(f"/api/v1/drafts/{seeded_draft}/analysis/run")
    my_runs = (await client.get("/api/v1/analysis/history")).json()
    assert len(my_runs) == 1
    run_id = my_runs[0]["run_id"]

    # A different user sees no runs and cannot view this one.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as other:
        resp = await other.post(
            "/api/v1/auth/register",
            json={"email": "other@example.com", "password": "password123"},
        )
        assert resp.status_code == 201
        text = email_stub.messages[-1][2]
        token = re.search(r"token=([A-Za-z0-9_\-]+)", text).group(1)
        await other.post("/api/v1/auth/activate", json={"token": token})

        assert (await other.get("/api/v1/analysis/history")).json() == []
        assert (await other.get(f"/api/v1/analysis/history/{run_id}")).status_code == 404


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
