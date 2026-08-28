from pydantic import BaseModel, EmailStr, Field


class UserProfileFields(BaseModel):
    """Optional contact/profile details shared by register, profile, and
    admin user management."""

    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=255)
    affiliation: str | None = Field(default=None, max_length=255)
    bio: str | None = Field(default=None, max_length=2000)


class RegisterRequest(UserProfileFields):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ActivateRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class UpdateProfileRequest(UserProfileFields):
    full_name: str | None = Field(default=None, max_length=120)


class AuthSessionStatus(BaseModel):
    authenticated: bool
    email: str | None = None
    role: str | None = None
    full_name: str | None = None
    phone: str | None = None
    address: str | None = None
    affiliation: str | None = None
    bio: str | None = None
