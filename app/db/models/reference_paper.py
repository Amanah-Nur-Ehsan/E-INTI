import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.db.models.enums import EnrichmentStatus

EMBEDDING_DIM = 768


class ReferencePaper(UUIDPrimaryKey, TimestampMixin, Base):
    """A candidate reference from the user's uploaded dataset.

    Named `reference_papers` rather than the spec's `references` because
    REFERENCES is a reserved SQL word that would need quoting everywhere.
    """

    __tablename__ = "reference_papers"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
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

    project: Mapped["Project"] = relationship(back_populates="references")  # noqa: F821

    # Partial unique indexes: rows we could not identify keep doi/eid NULL and
    # must not collide with each other.
    __table_args__ = (
        Index(
            "uq_reference_papers_project_id_doi",
            "project_id",
            "doi",
            unique=True,
            postgresql_where=text("doi IS NOT NULL"),
        ),
        Index(
            "uq_reference_papers_project_id_scopus_eid",
            "project_id",
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
