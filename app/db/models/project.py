import uuid

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class Project(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    field_of_study: Mapped[str | None] = mapped_column(Text)
    citation_style: Mapped[str] = mapped_column(Text, default="APA", server_default="APA")
    #: Nullable and unenforced for now -- this MVP is explicitly single-user
    #: (see the product spec's exclusions). Added ahead of need because
    #: retrofitting tenancy across populated collections/projects tables
    #: later is materially more expensive than adding an unused column now.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)

    drafts: Mapped[list["Draft"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
    references: Mapped[list["ReferencePaper"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
