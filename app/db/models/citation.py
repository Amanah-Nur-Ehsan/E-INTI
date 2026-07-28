import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.db.models.enums import InsertionMode, UserDecision


class CitationRecommendation(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "citation_recommendations"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reference_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("reference_papers.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    semantic_similarity: Mapped[float | None] = mapped_column(Float)
    lexical_similarity: Mapped[float | None] = mapped_column(Float)
    keyword_overlap: Mapped[float | None] = mapped_column(Float)
    field_match: Mapped[float | None] = mapped_column(Float)
    reranker_score: Mapped[float | None] = mapped_column(Float)
    llm_support_score: Mapped[float | None] = mapped_column(Float)

    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    score_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    recommendation_label: Mapped[str | None] = mapped_column(Text)

    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_usage: Mapped[str | None] = mapped_column(Text)
    evidence_paraphrase: Mapped[str | None] = mapped_column(Text)
    limitations: Mapped[str | None] = mapped_column(Text)

    user_decision: Mapped[str] = mapped_column(
        Text, default=UserDecision.PENDING, server_default=UserDecision.PENDING
    )
    user_note: Mapped[str | None] = mapped_column(Text)

    claim: Mapped["Claim"] = relationship(back_populates="recommendations")  # noqa: F821

    __table_args__ = (UniqueConstraint("claim_id", "reference_id"),)


class AcceptedCitation(UUIDPrimaryKey, Base):
    __tablename__ = "accepted_citations"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False
    )
    reference_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("reference_papers.id", ondelete="CASCADE"), nullable=False
    )
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("citation_recommendations.id", ondelete="SET NULL")
    )

    citation_text: Mapped[str | None] = mapped_column(Text)
    insertion_format: Mapped[str | None] = mapped_column(Text)
    insertion_mode: Mapped[str] = mapped_column(
        Text, default=InsertionMode.TRACKED_CHANGES, server_default=InsertionMode.TRACKED_CHANGES
    )
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("claim_id", "reference_id"),)


class LLMVerificationCache(UUIDPrimaryKey, Base):
    """Cache of Tier-2 verdicts keyed by (claim_hash, reference_id).

    Lets edits elsewhere in the draft avoid re-verifying unchanged claims.
    """

    __tablename__ = "llm_verification_cache"

    claim_hash: Mapped[str] = mapped_column(Text, nullable=False)
    reference_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("reference_papers.id", ondelete="CASCADE"), nullable=False
    )
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("claim_hash", "reference_id"),)
