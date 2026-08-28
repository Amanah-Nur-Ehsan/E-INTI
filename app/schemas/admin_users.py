import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.db.models.enums import UserRole
from app.schemas.auth import UserProfileFields


class UserAdminRead(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    phone: str | None
    address: str | None
    affiliation: str | None
    bio: str | None
    role: str
    is_active: bool
    email_verified_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateUserAdminRequest(UserProfileFields):
    full_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class ResetPasswordAdminRequest(BaseModel):
    new_password: str = Field(min_length=8)
