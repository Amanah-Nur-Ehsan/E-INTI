from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.db.models.enums import EnrichmentStatus

EMBEDDING_DIM = 768


class ReferencePaper(UUIDPrimaryKey, TimestampMixin, Base):
    """A candidate reference in the shared library.

    Global, not scoped to any project or draft: every uploaded paper
    queries the same pool, and enrichment/embedding cost -- the scarce
    resource -- is paid once per paper regardless of how many drafts
    end up citing it.

    Named `reference_papers` rather than the spec's `references` because
    REFERENCES is a reserved SQL word that would need quoting everywhere.
    """

    __tablename__ = "reference_papers"

    original_row_number: Mapped[int | None] = mapped_column(Integer)
    original_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text)
    authors: Mapped[list | None] = mapped_column(JSONB)
    year: Mapped[int | None] = mapped_column(Integer)
    source_title: Mapped[str | None] = mapped_column(Text)
    field_of_study: Mapped[str | None] = mapped_column(Text)

    doi: Mapped[str | None] = mapped_column(Text)
    scopus_eid: Mapped[str | None] = mapped_column(Text)
    scopus_id: Mapped[str | None] = mapped_column(Text)
    semantic_scholar_id: Mapped[str | None] = mapped_column(Text)

    author_keywords: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    index_keywords: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    subject_areas: Mapped[list[str] | None] = mapped_column(ARRAY(Text))

    source_link: Mapped[str | None] = mapped_column(Text)
    scopus_url: Mapped[str | None] = mapped_column(Text)
    publisher_url: Mapped[str | None] = mapped_column(Text)
    citation_count: Mapped[int | None] = mapped_column(Integer)
    document_type: Mapped[str | None] = mapped_column(Text)

    enrichment_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=EnrichmentStatus.PENDING,
        server_default=EnrichmentStatus.PENDING,
    )
    enrichment_provider: Mapped[str | None] = mapped_column(Text)
    enrichment_error: Mapped[str | None] = mapped_column(Text)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(Text)
    #: sha256 of the embedded text; drives re-embed-only-changed.
    content_hash: Mapped[str | None] = mapped_column(Text)

    # Global partial unique indexes: rows we could not identify keep doi/eid
    # NULL and must not collide with each other.
    __table_args__ = (
        Index(
            "uq_reference_papers_doi",
            "doi",
            unique=True,
            postgresql_where=text("doi IS NOT NULL"),
        ),
        Index(
            "uq_reference_papers_scopus_eid",
            "scopus_eid",
            unique=True,
            postgresql_where=text("scopus_eid IS NOT NULL"),
        ),
        Index(
            "ix_reference_papers_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
