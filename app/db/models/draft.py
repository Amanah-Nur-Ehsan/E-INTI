from datetime import datetime

from sqlalchemy import DateTime, Integer, Text
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

    #: One SDG (1-17) classified for the whole paper, set once during
    #: analysis. sdg_keyword is the specific keyword phrase (from
    #: app/data/sdg_goals.json) the LLM grounded its pick in -- see
    #: app/services/sdg_classification_service.py.
    sdg_number: Mapped[int | None] = mapped_column(Integer)
    sdg_name: Mapped[str | None] = mapped_column(Text)
    sdg_keyword: Mapped[str | None] = mapped_column(Text)
    #: One sentence on why this goal was picked -- the keyword alone doesn't
    #: explain the match, and a bare "SDG 3" invites doubt the user can't check.
    sdg_rationale: Mapped[str | None] = mapped_column(Text)

    #: Set only when the classifier declined (sdg_number is null): the
    #: best-ranked candidate it considered but judged not a genuine fit.
    #: Shown to the user as an unconfirmed "closest candidate", never
    #: written into the exported docx -- see classify_draft's `fits` field
    #: in app/services/sdg_classification_service.py.
    sdg_closest_number: Mapped[int | None] = mapped_column(Integer)
    sdg_closest_name: Mapped[str | None] = mapped_column(Text)

    claims: Mapped[list["Claim"]] = relationship(  # noqa: F821
        back_populates="draft", cascade="all, delete-orphan"
    )
