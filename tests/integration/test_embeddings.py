import numpy as np
import pytest
from sqlalchemy import select, text

from app.db.models import ReferencePaper
from app.services.embedding_service import (
    embed_project_references,
    fake_embed,
    reference_embedding_text,
)
from app.services.enrichment import enrich_project_references
from tests.conftest import FIXTURES

pytestmark = pytest.mark.integration


async def _enriched_project(client, db_session):
    project_id = (await client.post("/api/v1/projects", json={"name": "P"})).json()["id"]
    data = (FIXTURES / "sample_dataset.xlsx").read_bytes()
    await client.post(
        f"/api/v1/projects/{project_id}/references/import",
        files={"file": ("sample_dataset.xlsx", data)},
    )
    enrich_project_references(db_session, project_id)
    return project_id


def test_fake_embeddings_are_normalized_and_overlap_aware():
    vectors = fake_embed(
        [
            "machine learning fraud detection in financial transactions",
            "machine learning fraud detection for payment fraud",
            "sonnet structure in renaissance poetry",
        ]
    )
    assert vectors.shape == (3, 768)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)
    related = float(vectors[0] @ vectors[1])
    unrelated = float(vectors[0] @ vectors[2])
    assert related > unrelated


def test_reference_embedding_text_uses_title_sep_abstract():
    reference = ReferencePaper(
        title="A Title",
        abstract="An abstract.",
        author_keywords=["alpha", "beta"],
        original_data={},
    )
    built = reference_embedding_text(reference, separator="[SEP]")
    assert built.startswith("A Title[SEP]An abstract.")
    assert "Keywords: alpha; beta" in built


async def test_embeds_references_with_abstracts_only(client, db_session):
    project_id = await _enriched_project(client, db_session)

    counts = embed_project_references(db_session, project_id)
    assert counts["embedded"] == 10  # 7 dataset + 3 enriched
    assert counts["no_abstract"] == 2
    assert counts["skipped"] == 0

    stored = db_session.execute(
        select(ReferencePaper).where(
            ReferencePaper.project_id == project_id, ReferencePaper.embedding.isnot(None)
        )
    ).scalars()
    stored = list(stored)
    assert len(stored) == 10
    assert all(len(r.embedding) == 768 for r in stored)
    assert all(r.content_hash and r.embedding_model for r in stored)


async def test_reembeds_only_changed_content(client, db_session):
    project_id = await _enriched_project(client, db_session)
    embed_project_references(db_session, project_id)

    second = embed_project_references(db_session, project_id)
    assert second["embedded"] == 0
    assert second["skipped"] == 10

    changed = db_session.execute(
        select(ReferencePaper).where(
            ReferencePaper.project_id == project_id, ReferencePaper.abstract.isnot(None)
        )
    ).scalars().first()
    changed.abstract = changed.abstract + " An additional sentence changes the hash."
    db_session.commit()

    third = embed_project_references(db_session, project_id)
    assert third["embedded"] == 1
    assert third["skipped"] == 9


async def test_pgvector_nearest_neighbour_query(client, db_session):
    """The HNSW/cosine path returns the topically closest reference first."""
    project_id = await _enriched_project(client, db_session)
    embed_project_references(db_session, project_id)

    query = fake_embed(
        [
            "machine learning techniques improved the ability to identify complex fraud "
            "patterns in financial transactions"
        ]
    )[0]

    rows = db_session.execute(
        text(
            "SELECT title, 1 - (embedding <=> CAST(:v AS vector)) AS similarity "
            "FROM reference_papers "
            "WHERE project_id = CAST(:pid AS uuid) AND embedding IS NOT NULL "
            "ORDER BY embedding <=> CAST(:v AS vector) LIMIT 3"
        ),
        {"v": str(query.tolist()), "pid": str(project_id)},
    ).all()

    assert rows[0][0] == "Machine Learning Methods for Financial Fraud Detection"
    assert rows[0][1] > 0.3
