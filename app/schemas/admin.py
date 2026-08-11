from pydantic import BaseModel


class AdminLoginRequest(BaseModel):
    password: str


class AdminSessionStatus(BaseModel):
    authenticated: bool
