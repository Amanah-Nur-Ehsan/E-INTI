from datetime import datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.db.models.enums import ParseStatus


class Draft(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "drafts"

    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)

    #: Canonical text; every claim char offset indexes into this string.
    raw_text: Mapped[str | None] = mapped_column(Text)
    #: {"blocks": [...], "sentences": [...]} produced by the draft parser.
    parsed_content: Mapped[dict | None] = mapped_column(JSONB)
    language_code: Mapped[str] = mapped_column(Text, default="en", server_default="en")

    parse_status: Mapped[str] = mapped_column(
        Text, default=ParseStatus.PENDING, server_default=ParseStatus.PENDING
    )
    parse_error: Mapped[str | None] = mapped_column(Text)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    claims: Mapped[list["Claim"]] = relationship(  # noqa: F821
        back_populates="draft", cascade="all, delete-orphan"
    )
