"""Admin login/logout/session. See app/core/security.py for the session
and CSRF mechanics this wraps.
"""

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import AdminDep
from app.core.security import (
    check_password,
    create_admin_session,
    destroy_admin_session,
    is_login_locked_out,
    record_login_failure,
    reset_login_failures,
)
from app.schemas.admin import AdminLoginRequest, AdminSessionStatus

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
async def login(body: AdminLoginRequest, response: Response) -> None:
    if await is_login_locked_out():
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed login attempts. Try again later.",
        )

    if not check_password(body.password):
        await record_login_failure()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect password")

    await reset_login_failures()
    await create_admin_session(response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, _admin: AdminDep) -> None:
    await destroy_admin_session(request, response)


@router.get("/session", response_model=AdminSessionStatus)
async def session_status(_admin: AdminDep) -> AdminSessionStatus:
    # Reaching this point at all means require_admin already validated the
    # cookie -- a bare 200 here is the "yes, still logged in" signal the
    # frontend polls to decide login-form-vs-dashboard.
    return AdminSessionStatus(authenticated=True)
