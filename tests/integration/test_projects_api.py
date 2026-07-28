import pytest

pytestmark = pytest.mark.integration


async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["db"] == "up"
    assert body["redis"] == "up"


async def test_project_crud_roundtrip(client):
    created = await client.post(
        "/api/v1/projects",
        json={"name": "Fraud detection review", "field_of_study": "Computer Science"},
    )
    assert created.status_code == 201
    project = created.json()
    assert project["citation_style"] == "APA"

    fetched = await client.get(f"/api/v1/projects/{project['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Fraud detection review"

    patched = await client.patch(
        f"/api/v1/projects/{project['id']}", json={"description": "MVP trial"}
    )
    assert patched.json()["description"] == "MVP trial"

    listed = await client.get("/api/v1/projects")
    assert len(listed.json()) == 1

    deleted = await client.delete(f"/api/v1/projects/{project['id']}")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/projects/{project['id']}")).status_code == 404
