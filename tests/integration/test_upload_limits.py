import pytest

from app.core.config import get_settings

pytestmark = pytest.mark.integration


async def test_draft_upload_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)

    oversized = b"x" * (2 * 1024 * 1024)  # 2 MiB > 1 MiB cap
    resp = await client.post(
        "/api/v1/drafts/upload",
        files={"file": ("big.txt", oversized)},
    )
    assert resp.status_code == 413


async def test_reference_import_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)

    oversized = b"NO.,TITLE,LINK\n" + b"x" * (2 * 1024 * 1024)
    resp = await client.post(
        "/api/v1/library/import",
        files={"file": ("big.csv", oversized)},
    )
    assert resp.status_code == 413


async def test_draft_upload_within_cap_succeeds(client):
    small = b"Some short draft text.\n\nAnother paragraph here."
    resp = await client.post(
        "/api/v1/drafts/upload",
        files={"file": ("small.txt", small)},
    )
    assert resp.status_code == 201
