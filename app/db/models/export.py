import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.db.models.enums import InsertionMode


class Export(UUIDPrimaryKey, TimestampMixin, Base):
    """A generated export artifact, kept on disk with metadata here so the
    review UI can warn about skipped citations (POSITION_MISMATCH) before
    the user downloads the file, and so past exports can be listed.
    """

    __tablename__ = "exports"

    draft_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False
    )

    format: Mapped[str] = mapped_column(Text, nullable=False)
    citation_style: Mapped[str] = mapped_column(Text, default="APA", server_default="APA")
    insertion_mode: Mapped[str] = mapped_column(
        Text, default=InsertionMode.TRACKED_CHANGES, server_default=InsertionMode.TRACKED_CHANGES
    )
    include_audit_report: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)

    inserted_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    mismatch_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    #: Per-claim outcome details (claim_id, status, citation_text) for the UI.
    outcomes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
