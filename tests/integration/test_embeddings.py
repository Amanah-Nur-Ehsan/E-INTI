import numpy as np
import pytest
from sqlalchemy import select, text

from app.db.models import ReferencePaper
from app.services.embedding_service import (
    embed_pending_references,
    fake_embed,
    mark_embedding_stale,
    reference_embedding_text,
)
from app.services.enrichment import enrich_pending_references
from tests.conftest import FIXTURES

pytestmark = pytest.mark.integration


async def _enriched_library(client, db_session):
    data = (FIXTURES / "sample_dataset.xlsx").read_bytes()
    await client.post(
        "/api/v1/library/import",
        files={"file": ("sample_dataset.xlsx", data)},
    )
    enrich_pending_references(db_session)


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
    await _enriched_library(client, db_session)

    counts = embed_pending_references(db_session)
    assert counts["embedded"] == 10  # 7 dataset + 3 enriched
    assert counts["no_abstract"] == 2
    assert counts["skipped"] == 0

    stored = db_session.execute(
        select(ReferencePaper).where(ReferencePaper.embedding.isnot(None))
    ).scalars()
    stored = list(stored)
    assert len(stored) == 10
    assert all(len(r.embedding) == 768 for r in stored)
    assert all(r.content_hash and r.embedding_model for r in stored)


async def test_reembeds_only_changed_content(client, db_session):
    await _enriched_library(client, db_session)
    embed_pending_references(db_session)

    # Every row is already embedded and current, so the SQL-side
    # content_hash IS NULL filter selects nothing -- there's no longer a
    # "candidate found current, skipped" case in the normal path (that was
    # the shape of the original livelock: the same already-current rows
    # kept being re-selected and skipped, forever).
    second = embed_pending_references(db_session)
    assert second["embedded"] == 0
    assert second["skipped"] == 0
    assert second["remaining"] == 0

    changed = (
        db_session.execute(
            select(ReferencePaper).where(ReferencePaper.abstract.isnot(None))
        )
        .scalars()
        .first()
    )
    changed.abstract = changed.abstract + " An additional sentence changes the hash."
    mark_embedding_stale(changed)  # what a real writer (apply_result, import) now does
    db_session.commit()

    third = embed_pending_references(db_session)
    assert third["embedded"] == 1
    assert third["skipped"] == 0
    assert third["remaining"] == 0


async def test_pgvector_nearest_neighbour_query(client, db_session):
    """The HNSW/cosine path returns the topically closest reference first."""
    await _enriched_library(client, db_session)
    embed_pending_references(db_session)

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
            "WHERE embedding IS NOT NULL "
            "ORDER BY embedding <=> CAST(:v AS vector) LIMIT 3"
        ),
        {"v": str(query.tolist())},
    ).all()

    assert rows[0][0] == "Machine Learning Methods for Financial Fraud Detection"
    assert rows[0][1] > 0.3
