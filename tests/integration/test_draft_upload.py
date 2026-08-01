import pytest

from app.db.models import Draft
from app.db.models.enums import ParseStatus
from app.services.draft_parser_service import parse_and_store_draft
from tests.conftest import FIXTURES

pytestmark = pytest.mark.integration


async def upload_draft(client, filename="sample_draft.docx"):
    data = (FIXTURES / filename).read_bytes()
    return await client.post(
        "/api/v1/drafts/upload",
        files={"file": (filename, data)},
    )


async def test_upload_stores_file_and_metadata(client, db_session):
    resp = await upload_draft(client)
    assert resp.status_code == 201

    body = resp.json()
    assert body["original_filename"] == "sample_draft.docx"
    assert body["parse_status"] == ParseStatus.PENDING

    draft = db_session.get(Draft, body["id"])
    from pathlib import Path

    assert Path(draft.storage_path).exists()


async def test_upload_rejects_pdf(client):
    resp = await client.post(
        "/api/v1/drafts/upload",
        files={"file": ("paper.pdf", b"%PDF-1.4")},
    )
    assert resp.status_code == 422
    assert ".pdf" in resp.json()["detail"]


async def test_parse_stage_persists_text_and_sentences(client, db_session):
    draft_id = (await upload_draft(client)).json()["id"]

    summary = parse_and_store_draft(db_session, draft_id)
    assert summary["blocks"] > 0
    assert summary["sentences"] > 5

    detail = (await client.get(f"/api/v1/drafts/{draft_id}")).json()
    assert detail["parse_status"] == ParseStatus.PARSED
    assert detail["parsed_at"] is not None
    assert detail["raw_text"].startswith("Adaptive Machine Learning")

    sentences = detail["parsed_content"]["sentences"]
    raw = detail["raw_text"]
    # The stored offsets must still slice back out of the stored raw_text.
    for sentence in sentences:
        assert raw[sentence["char_start"] : sentence["char_end"]] == sentence["text"]


async def test_parse_failure_is_recorded_on_the_draft(client, db_session, tmp_path):
    draft_id = (await upload_draft(client)).json()["id"]

    draft = db_session.get(Draft, draft_id)
    corrupt = tmp_path / "broken.docx"
    corrupt.write_bytes(b"not a real docx")
    draft.storage_path = str(corrupt)
    db_session.commit()

    from docx.opc.exceptions import PackageNotFoundError

    with pytest.raises(PackageNotFoundError):
        parse_and_store_draft(db_session, draft_id)

    db_session.refresh(draft)
    assert draft.parse_status == ParseStatus.FAILED
    assert draft.parse_error
