import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class User(UUIDPrimaryKey, TimestampMixin, Base):
    """A registered account. Activation is gated by `is_active` (the
    account is created inactive and only flipped by a valid activation
    token); `email_verified_at` is an audit timestamp, not the gate.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, default="user", server_default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserToken(UUIDPrimaryKey, Base):
    """Single-use token for account activation or password reset.

    Only the SHA-256 of the token is stored (a DB dump is not live
    credentials), and the row is deleted on successful use -- both the
    single-use and revocation semantics live in the database, so they
    survive restarts and don't depend on Redis.
    """

    __tablename__ = "user_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
