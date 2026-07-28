import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.db.models.enums import ExistingCitationStatus, ReviewStatus


class Claim(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "claims"

    draft_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    section_title: Mapped[str | None] = mapped_column(Text)
    paragraph_index: Mapped[int | None] = mapped_column(Integer)
    sentence_index: Mapped[int | None] = mapped_column(Integer)
    #: Offsets index into drafts.raw_text.
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)

    sentence_text: Mapped[str] = mapped_column(Text, nullable=False)
    local_context: Mapped[str] = mapped_column(Text, nullable=False)
    claim_text: Mapped[str | None] = mapped_column(Text)

    needs_citation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    claim_type: Mapped[str | None] = mapped_column(Text)
    claim_confidence: Mapped[float | None] = mapped_column(Float)
    detection_method: Mapped[str | None] = mapped_column(Text)

    existing_citation_text: Mapped[str | None] = mapped_column(Text)
    existing_citation_status: Mapped[str] = mapped_column(
        Text,
        default=ExistingCitationStatus.NO_CITATION_FOUND,
        server_default=ExistingCitationStatus.NO_CITATION_FOUND,
    )
    review_status: Mapped[str] = mapped_column(
        Text, default=ReviewStatus.PENDING, server_default=ReviewStatus.PENDING
    )

    #: sha256 of the normalized claim text; verification cache key.
    claim_hash: Mapped[str | None] = mapped_column(Text)
    #: Noun-chunk lemmas used for keyword overlap scoring.
    keywords: Mapped[list | None] = mapped_column(JSONB)

    draft: Mapped["Draft"] = relationship(back_populates="claims")  # noqa: F821
    recommendations: Mapped[list["CitationRecommendation"]] = relationship(  # noqa: F821
        back_populates="claim", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_claims_claim_hash", "claim_hash"),)
