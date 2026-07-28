import pytest
from sqlalchemy import select

from app.db.models import ReferencePaper
from app.db.models.enums import EnrichmentProvider, EnrichmentStatus
from app.services.enrichment import enrich_project_references
from tests.conftest import FIXTURES

pytestmark = pytest.mark.integration


async def _project_with_dataset(client):
    project_id = (await client.post("/api/v1/projects", json={"name": "P"})).json()["id"]
    data = (FIXTURES / "sample_dataset.xlsx").read_bytes()
    await client.post(
        f"/api/v1/projects/{project_id}/references/import",
        files={"file": ("sample_dataset.xlsx", data)},
    )
    return project_id


async def test_enrichment_fills_withheld_abstracts(client, db_session):
    project_id = await _project_with_dataset(client)

    counts = enrich_project_references(db_session, project_id)
    # Rows 4, 6, 9 resolve from Scopus fixtures; rows 11 and 12 cannot.
    assert counts == {"enriched": 3, "incomplete": 2, "failed": 0}

    refs = {
        r.original_row_number: r
        for r in db_session.execute(
            select(ReferencePaper).where(ReferencePaper.project_id == project_id)
        ).scalars()
    }

    filled = refs[4]
    assert filled.enrichment_status == EnrichmentStatus.ENRICHED
    assert filled.enrichment_provider == EnrichmentProvider.SCOPUS
    assert "cost-sensitive" in filled.abstract
    assert filled.author_keywords == ["class imbalance", "anomaly detection", "SMOTE"]
    assert filled.enriched_at is not None

    from_bibrecord = refs[6]
    assert from_bibrecord.abstract.startswith("Payment systems form dense")

    unresolvable = refs[11]
    assert unresolvable.enrichment_status == EnrichmentStatus.INCOMPLETE
    assert unresolvable.abstract is None
    assert "No abstract retrieved" in unresolvable.enrichment_error

    no_identifier = refs[12]
    assert no_identifier.enrichment_status == EnrichmentStatus.INCOMPLETE

    # Dataset-supplied abstracts are left untouched.
    assert refs[1].enrichment_provider == EnrichmentProvider.DATASET


async def test_enrichment_is_idempotent(client, db_session):
    project_id = await _project_with_dataset(client)
    enrich_project_references(db_session, project_id)
    second = enrich_project_references(db_session, project_id)
    assert second == {"enriched": 0, "incomplete": 0, "failed": 0}


async def test_pipeline_stage_reports_enrichment_progress(client, seeded_project):
    project_id = seeded_project
    resp = await client.post(f"/api/v1/projects/{project_id}/analysis/run", json={})
    assert resp.status_code == 202

    status = (await client.get(f"/api/v1/projects/{project_id}/analysis/status")).json()
    assert status["status"] == "COMPLETED"
    # 7 arrived with dataset abstracts, 3 more were fetched from Scopus.
    assert status["references"]["enriched"] == 10
    assert status["references"]["incomplete"] == 2
    assert status["references"]["pending"] == 0
