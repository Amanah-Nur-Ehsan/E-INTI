from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
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


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)


class AuthSessionStatus(BaseModel):
    authenticated: bool
    email: str | None = None
    role: str | None = None
    full_name: str | None = None
