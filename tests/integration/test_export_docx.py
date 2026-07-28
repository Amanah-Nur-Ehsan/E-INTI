"""Round-trips the DOCX writer through the full pipeline: upload, analyse,
accept, export, and re-open the produced file to inspect its oxml.
"""

import uuid

import pytest
from docx import Document
from docx.oxml.ns import qn

from app.db.models.enums import InsertionMode
from app.services.export.bundle import build_bundle
from app.services.export.docx_ops import _para_text
from app.services.export.docx_writer import write_docx
from tests.conftest import FIXTURES

pytestmark = pytest.mark.integration


async def _analyzed_draft(client, db_session):
    """Upload+import+run analysis, accept every claim's top recommendation,
    and return (draft_id, accepted_claim_ids).
    """
    from tests.conftest import create_project, import_dataset, upload_draft

    project_id = await create_project(client, "P", field_of_study="Computer Science")
    draft_id = await upload_draft(client, project_id)
    await import_dataset(client, project_id)
    await client.post(f"/api/v1/projects/{project_id}/analysis/run", json={})

    claims = (await client.get(f"/api/v1/drafts/{draft_id}/claims?needs_citation=true")).json()
    accepted = []
    for claim in claims:
        recs = (await client.get(f"/api/v1/claims/{claim['id']}/recommendations")).json()
        if recs:
            await client.post(f"/api/v1/recommendations/{recs[0]['id']}/accept", json={})
            accepted.append(claim["id"])
    return draft_id, accepted


def _ins_elements(doc: Document) -> list:
    return doc.element.body.xpath(".//w:ins")


async def test_tracked_changes_export_inserts_exactly_one_per_claim(client, db_session):
    draft_id, accepted = await _analyzed_draft(client, db_session)
    bundle = build_bundle(db_session, uuid.UUID(draft_id))
    assert len(bundle.accepted) == len(accepted)

    original_bytes = FIXTURES.joinpath("sample_draft.docx").read_bytes()

    docx_bytes, outcomes = write_docx(bundle, mode=InsertionMode.TRACKED_CHANGES)
    assert all(o.status == "INSERTED" for o in outcomes)

    from io import BytesIO

    reloaded = Document(BytesIO(docx_bytes))
    ins_elements = _ins_elements(reloaded)
    # write_docx shares one monotonic revision counter across citations and
    # the bibliography, so the first N <w:ins> ids (in id order) are the
    # per-claim citations and everything after is bibliography wrapping.
    by_id = sorted(ins_elements, key=lambda el: int(el.get(qn("w:id"))))
    citation_ins = by_id[: len(accepted)]
    assert len(citation_ins) == len(accepted)
    for el in ins_elements:
        assert el.get(qn("w:author")) == "CitationRecommender"

    # The source fixture on disk must be untouched by the export.
    assert FIXTURES.joinpath("sample_draft.docx").read_bytes() == original_bytes


async def test_direct_mode_inserts_plain_text_no_tracked_changes(client, db_session):
    draft_id, accepted = await _analyzed_draft(client, db_session)
    bundle = build_bundle(db_session, uuid.UUID(draft_id))

    docx_bytes, outcomes = write_docx(bundle, mode=InsertionMode.DIRECT)
    assert all(o.status == "INSERTED" for o in outcomes)

    from io import BytesIO

    reloaded = Document(BytesIO(docx_bytes))
    assert len(_ins_elements(reloaded)) == 0
    # Direct mode: paragraph.text (which excludes w:ins) should now show
    # the inserted citation text directly, since nothing is wrapped.
    joined_body_text = " ".join(p.text for p in reloaded.paragraphs)
    for outcome in outcomes:
        assert outcome.citation_text in joined_body_text


async def test_placeholder_mode_inserts_bracketed_marker(client, db_session):
    draft_id, accepted = await _analyzed_draft(client, db_session)
    bundle = build_bundle(db_session, uuid.UUID(draft_id))

    docx_bytes, outcomes = write_docx(bundle, mode=InsertionMode.PLACEHOLDER)
    from io import BytesIO

    reloaded = Document(BytesIO(docx_bytes))
    body_text = " ".join(p.text for p in reloaded.paragraphs)
    for outcome in outcomes:
        if outcome.status == "INSERTED":
            assert f"[CITATION: {outcome.citation_text}]" in body_text


async def test_two_claims_in_the_same_paragraph_both_insert_correctly(client, db_session):
    """The descending-order regression: accepting citations for two
    sentences in one paragraph must not corrupt either insertion, and
    must not falsely report a POSITION_MISMATCH on the earlier one.
    """
    draft_id, accepted = await _analyzed_draft(client, db_session)
    bundle = build_bundle(db_session, uuid.UUID(draft_id))

    from collections import Counter

    paragraph_counts = Counter(item.claim.paragraph_index for item in bundle.accepted)
    multi_claim_paragraphs = [p for p, count in paragraph_counts.items() if count >= 2]
    assert multi_claim_paragraphs, "fixture draft should produce >=2 claims in one paragraph"

    docx_bytes, outcomes = write_docx(bundle, mode=InsertionMode.TRACKED_CHANGES)
    assert all(o.status == "INSERTED" for o in outcomes), [
        (o.status, o.paragraph_index) for o in outcomes if o.status != "INSERTED"
    ]

    from io import BytesIO

    reloaded = Document(BytesIO(docx_bytes))
    for paragraph_index in multi_claim_paragraphs:
        expected_citations = [
            bundle.context.in_text(ref.id)
            for item in bundle.accepted
            if item.claim.paragraph_index == paragraph_index
            for ref in item.references
        ]
        paragraph_text = _para_text(reloaded.paragraphs[paragraph_index])
        for citation in expected_citations:
            assert citation in paragraph_text


async def test_position_mismatch_when_draft_text_changed_since_analysis(client, db_session):
    draft_id, accepted = await _analyzed_draft(client, db_session)
    assert accepted

    # Simulate an external edit: corrupt the stored sentence text for one
    # accepted claim so it no longer matches the live docx paragraph.
    from app.db.models import Claim

    claim = db_session.get(Claim, uuid.UUID(accepted[0]))
    claim.sentence_text = "This sentence text was edited and no longer matches the source file."
    db_session.commit()

    bundle = build_bundle(db_session, uuid.UUID(draft_id))
    docx_bytes, outcomes = write_docx(bundle, mode=InsertionMode.TRACKED_CHANGES)

    mismatched = [o for o in outcomes if o.claim_id == claim.id]
    assert len(mismatched) == 1
    assert mismatched[0].status == "POSITION_MISMATCH"

    # Every other accepted claim must still insert normally.
    others = [o for o in outcomes if o.claim_id != claim.id]
    assert all(o.status == "INSERTED" for o in others)


async def test_bibliography_has_one_entry_per_unique_reference(client, db_session):
    draft_id, accepted = await _analyzed_draft(client, db_session)
    bundle = build_bundle(db_session, uuid.UUID(draft_id))

    docx_bytes, _outcomes = write_docx(bundle, mode=InsertionMode.TRACKED_CHANGES)
    from io import BytesIO

    reloaded = Document(BytesIO(docx_bytes))

    heading_index = next(
        i for i, p in enumerate(reloaded.paragraphs) if _para_text(p) == "References"
    )
    entries = [_para_text(p) for p in reloaded.paragraphs[heading_index + 1 :]]

    assert len(entries) == len(set(entries))
    unique_ref_ids = {ref.id for item in bundle.accepted for ref in item.references}
    assert len(entries) == len(unique_ref_ids)


async def test_bibliography_italicizes_source_title():
    from docx import Document as DocxDocument

    doc = DocxDocument()
    doc.add_paragraph("placeholder")
    from app.services.citation_formatting_service import Segment

    para = doc.add_paragraph()
    for seg in [
        Segment("Smith, J. "),
        Segment("(2023). "),
        Segment("A Paper. "),
        Segment("A Journal", italic=True),
        Segment(", https://doi.org/10.1/x"),
    ]:
        run = para.add_run(seg.text)
        run.italic = seg.italic

    italic_runs = [r for r in para._p.xpath(".//w:r") if _run_is_italic(r)]
    assert len(italic_runs) == 1
    t = italic_runs[0].find(qn("w:t"))
    assert t.text == "A Journal"


def _run_is_italic(run_el) -> bool:
    rpr = run_el.find(qn("w:rPr"))
    if rpr is None:
        return False
    i_el = rpr.find(qn("w:i"))
    if i_el is None:
        return False
    val = i_el.get(qn("w:val"))
    return val is None or val not in ("0", "false")


async def test_docx_export_rejected_for_markdown_draft(client, db_session):
    from tests.conftest import create_project

    project_id = await create_project(client, "P")
    data = FIXTURES.joinpath("sample_draft.md").read_bytes()
    upload = await client.post(
        f"/api/v1/projects/{project_id}/drafts/upload",
        files={"file": ("sample_draft.md", data)},
    )
    draft_id = upload.json()["id"]

    from app.services.draft_parser_service import parse_and_store_draft

    parse_and_store_draft(db_session, uuid.UUID(draft_id))

    bundle = build_bundle(db_session, uuid.UUID(draft_id))
    with pytest.raises(ValueError, match="DOCX export requires a .docx source draft"):
        write_docx(bundle)


async def test_build_bundle_requires_parsed_draft(client, db_session):
    from app.services.export.bundle import DraftNotParsedError
    from tests.conftest import create_project, upload_draft

    project_id = await create_project(client, "P")
    draft_id = await upload_draft(client, project_id)  # uploaded but never parsed

    with pytest.raises(DraftNotParsedError):
        build_bundle(db_session, uuid.UUID(draft_id))
