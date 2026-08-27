import asyncio
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import SessionDep, UserDep
from app.core.config import get_settings
from app.core.security import (
    _legacy_admin_session_valid,
    _user_session_user_id,
    create_user_session,
    destroy_user_session,
    hash_password,
    record_user_login_failure,
    reset_user_login_failures,
    user_is_login_locked_out,
    verify_password,
)
from app.db.models import User, UserToken
from app.db.models.enums import UserRole, UserTokenKind
from app.schemas.auth import (
    ActivateRequest,
    AuthSessionStatus,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UpdateProfileRequest,
)
from app.services.email_client import EmailSender, get_email_sender

router = APIRouter(prefix="/auth", tags=["auth"])

EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _issue_token(
    session, user_id: uuid.UUID, kind: UserTokenKind, ttl_seconds: int
) -> str:
    """Create a single-use token row, returning the raw token (only its
    sha256 is stored). The row is deleted on successful use."""
    raw = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    session.add(
        UserToken(
            user_id=user_id,
            kind=kind,
            token_hash=_token_hash(raw),
            expires_at=expires_at,
        )
    )
    return raw


def _activation_email(link: str) -> tuple[str, str]:
    text = f"Activate your CitationINTI account:\n\n{link}\n\nThis link expires in 24 hours."
    html = (
        f'<p>Activate your CitationINTI account:</p>'
        f'<p><a href="{link}">{link}</a></p>'
    )
    return text, html


def _reset_email(link: str) -> tuple[str, str]:
    text = f"Reset your CitationINTI password:\n\n{link}\n\nThis link expires in 30 minutes."
    html = (
        f'<p>Reset your CitationINTI password:</p>'
        f'<p><a href="{link}">{link}</a></p>'
    )
    return text, html


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest, session: SessionDep, sender: EmailSenderDep
) -> dict:
    settings = get_settings()
    if not settings.registration_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is disabled")

    email = body.email.lower()
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with this email already exists"
        )

    full_name = body.full_name.strip() if body.full_name and body.full_name.strip() else None
    user = User(email=email, password_hash=hash_password(body.password), full_name=full_name)
    if email in settings.admin_emails_set:
        user.role = UserRole.ADMIN
    session.add(user)
    await session.flush()

    raw = await _issue_token(
        session, user.id, UserTokenKind.ACTIVATION, settings.activation_token_ttl_seconds
    )
    link = f"{settings.app_public_url}/activate?token={raw}"
    text, html = _activation_email(link)

    # Send before committing so a failed delivery rolls the whole account
    # back instead of leaving a half-registered, un-activatable user.
    try:
        await asyncio.to_thread(sender.send, email, "Activate your account", text, html)
    except Exception:
        await session.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Failed to send the activation email -- please try again",
        ) from None
    await session.commit()
    return {"email": email}


@router.post("/activate", status_code=status.HTTP_204_NO_CONTENT)
async def activate(body: ActivateRequest, session: SessionDep, response: Response) -> None:
    row = await session.scalar(
        select(UserToken).where(
            UserToken.token_hash == _token_hash(body.token),
            UserToken.kind == UserTokenKind.ACTIVATION,
        )
    )
    if row is None or row.expires_at < datetime.now(UTC):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired activation token")

    user = await session.get(User, row.user_id)
    user.is_active = True
    user.email_verified_at = datetime.now(UTC)
    await session.delete(row)
    await session.commit()
    # Auto-login after activation so the user lands on the app, not the login page.
    await create_user_session(response, str(user.id))


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
async def login(body: LoginRequest, session: SessionDep, response: Response) -> None:
    email = body.email.lower()
    if await user_is_login_locked_out(email):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts; try again later")

    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(body.password, user.password_hash):
        await record_user_login_failure(email)
        # One message for both unknown email and wrong password: no enumeration.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if not user.is_active:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Account not activated -- check your email for the activation link",
        )

    await reset_user_login_failures(email)
    await create_user_session(response, str(user.id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    await destroy_user_session(request, response)


@router.get("/session", response_model=AuthSessionStatus)
async def session_status(
    request: Request, response: Response, session: SessionDep
) -> AuthSessionStatus:
    user_id = await _user_session_user_id(request)
    if user_id:
        user = await session.get(User, uuid.UUID(user_id)) if _is_uuid(user_id) else None
        if user is not None and user.is_active:
            return AuthSessionStatus(
                authenticated=True, email=user.email, role=user.role, full_name=user.full_name
            )
        # Stale cookie: row gone or deactivated -- clear it and fall through.
        await destroy_user_session(request, response)

    if await _legacy_admin_session_valid(request):
        # Migration bridge: the shared-password admin is still an admin.
        return AuthSessionStatus(authenticated=True, role=UserRole.ADMIN)

    return AuthSessionStatus(authenticated=False)


@router.patch("/me", response_model=AuthSessionStatus)
async def update_profile(
    body: UpdateProfileRequest, user: UserDep, session: SessionDep
) -> AuthSessionStatus:
    """Update the signed-in user's profile (currently just their name)."""
    user.full_name = body.full_name.strip() if body.full_name and body.full_name.strip() else None
    await session.commit()
    return AuthSessionStatus(
        authenticated=True, email=user.email, role=user.role, full_name=user.full_name
    )


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(body: ForgotPasswordRequest, session: SessionDep, sender: EmailSenderDep) -> None:
    settings = get_settings()
    email = body.email.lower()
    user = await session.scalar(select(User).where(User.email == email))
    if user is not None and user.is_active:
        raw = await _issue_token(
            session, user.id, UserTokenKind.PASSWORD_RESET, settings.reset_token_ttl_seconds
        )
        await session.commit()
        link = f"{settings.app_public_url}/reset-password?token={raw}"
        text, html = _reset_email(link)
        await asyncio.to_thread(sender.send, email, "Reset your password", text, html)
    # Always 204 -- replying differently for unknown addresses leaks who is registered.


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(body: ResetPasswordRequest, session: SessionDep) -> None:
    row = await session.scalar(
        select(UserToken).where(
            UserToken.token_hash == _token_hash(body.token),
            UserToken.kind == UserTokenKind.PASSWORD_RESET,
        )
    )
    if row is None or row.expires_at < datetime.now(UTC):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired reset token")

    user = await session.get(User, row.user_id)
    user.password_hash = hash_password(body.new_password)
    await session.delete(row)
    await session.commit()


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False
