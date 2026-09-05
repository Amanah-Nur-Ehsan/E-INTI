import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey
from app.db.models.enums import RunStatus


class AnalysisRun(UUIDPrimaryKey, TimestampMixin, Base):
    """One end-to-end pipeline execution (enrich -> embed -> parse -> detect -> recommend).

    Progress is never stored as counters; the status endpoint derives it from
    live row counts so it cannot drift.
    """

    __tablename__ = "analysis_runs"

    draft_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False
    )

    #: User who triggered the run -- each user only sees their own history.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    status: Mapped[str] = mapped_column(
        Text, nullable=False, default=RunStatus.PENDING, server_default=RunStatus.PENDING
    )
    stage: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    celery_root_id: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Frozen snapshot of the completed run's full result (draft, SDG,
    #: claims, recommendations, accepted citations), so the History screen
    #: can show a past analysis even after the live rows change.
    result_json: Mapped[dict | None] = mapped_column(JSONB)

