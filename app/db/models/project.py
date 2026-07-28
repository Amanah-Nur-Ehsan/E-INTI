from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class Project(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    field_of_study: Mapped[str | None] = mapped_column(Text)
    citation_style: Mapped[str] = mapped_column(Text, default="APA", server_default="APA")

    drafts: Mapped[list["Draft"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
    references: Mapped[list["ReferencePaper"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
