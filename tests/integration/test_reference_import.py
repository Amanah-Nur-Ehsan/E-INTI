import pytest
from sqlalchemy import select

from app.db.models import ReferencePaper
from app.db.models.enums import EnrichmentProvider, EnrichmentStatus
from tests.conftest import FIXTURES

pytestmark = pytest.mark.integration


async def _import(client, filename="sample_dataset.xlsx"):
    data = (FIXTURES / filename).read_bytes()
    return await client.post(
        "/api/v1/library/import",
        files={"file": (filename, data)},
    )


async def test_import_xlsx_populates_references(client, db_session):
    resp = await _import(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["imported"] == 12
    assert body["skipped_duplicates"] == 0
    assert body["skipped_invalid"] == 0
    # Row 12 has no DOI/EID in its LINK.
    assert any("Row 12" in w for w in body["warnings"])

    refs = db_session.execute(select(ReferencePaper).order_by(ReferencePaper.original_row_number))
    refs = list(refs.scalars())
    assert len(refs) == 12

    first = refs[0]
    assert first.title.startswith("Machine Learning Methods")
    assert first.doi == "10.1016/j.eswa.2024.100001"
    assert first.year == 2024
    assert first.author_keywords == ["fraud detection", "machine learning", "financial transactions"]
    # Dataset already carried a full abstract -> trusted, no enrichment needed.
    assert first.enrichment_status == EnrichmentStatus.ENRICHED
    assert first.enrichment_provider == EnrichmentProvider.DATASET

    scopus_row = refs[1]
    assert scopus_row.scopus_eid == "2-s2.0-85100000002"

    no_abstract = refs[10]
    assert no_abstract.abstract is None
    assert no_abstract.enrichment_status == EnrichmentStatus.PENDING


async def test_reimport_skips_duplicates(client):
    await _import(client)
    second = await _import(client)
    assert second.json() == {
        "imported": 0,
        "skipped_duplicates": 12,
        "skipped_invalid": 0,
        "warnings": [],
    }


async def test_import_csv_equivalent_to_xlsx(client, db_session):
    resp = await _import(client, "sample_dataset.csv")
    assert resp.json()["imported"] == 12


async def test_import_rejects_dataset_without_required_columns(client):
    resp = await client.post(
        "/api/v1/library/import",
        files={"file": ("bad.csv", b"YEAR,AUTHORS\n2024,Smith\n")},
    )
    assert resp.status_code == 422
    assert "title" in resp.json()["detail"]


async def test_status_and_list_endpoints(client):
    await _import(client)

    status_body = (await client.get("/api/v1/library/status")).json()
    assert status_body["total"] == 12
    # Seven rows ship with usable abstracts; the rest await enrichment.
    assert status_body["enriched"] == 7
    assert status_body["pending"] == 5

    listed = (
        await client.get("/api/v1/library?enrichment_status=PENDING")
    ).json()
    assert {r["title"] for r in listed} == {
        "Class Imbalance Strategies for Transaction Anomaly Detection",
        "Graph Neural Networks for Payment Network Analysis",
        "Evaluation Metrics for Highly Imbalanced Binary Classification",
        "An Unindexed Workshop Paper on Transaction Screening",
        "Internal Technical Note on Alert Triage",
    }
