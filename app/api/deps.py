import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    _ensure_same_origin,
    _legacy_admin_session_valid,
    _user_session_user_id,
    destroy_user_session,
)
from app.db.models import Draft, User
from app.db.models.enums import UserRole
from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _active_user_from_cookie(request: Request, session: AsyncSession) -> User | None:
    """The user behind a valid cin_user cookie, or None. A stale or
    deactivated user's cookie is cleared here so it can't silently linger."""
    user_id = await _user_session_user_id(request)
    if not user_id:
        return None
    try:
        user = await session.get(User, uuid.UUID(user_id))
    except ValueError:
        return None
    if user is None or not user.is_active:
        return None
    return user


async def require_user(request: Request, response: Response, session: SessionDep) -> None:
    """Gate for the main app: any active user session, or (migration) the
    legacy shared-password admin session."""
    if await _active_user_from_cookie(request, session) is not None:
        _ensure_same_origin(request)
        return
    if await _legacy_admin_session_valid(request):
        _ensure_same_origin(request)
        return
    # If a user cookie existed but resolved to nothing usable, drop it.
    await destroy_user_session(request, response)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")


async def require_any_admin(request: Request, response: Response, session: SessionDep) -> None:
    """Gate for library/admin routes: a role=admin user, or (migration) the
    legacy shared-password admin session."""
    if await _legacy_admin_session_valid(request):
        _ensure_same_origin(request)
        return
    user = await _active_user_from_cookie(request, session)
    if user is not None and user.role == UserRole.ADMIN:
        _ensure_same_origin(request)
        return
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin login required")


async def get_current_user(request: Request, session: SessionDep) -> User:
    """The authenticated user row; 401 if only a legacy admin session (no
    user account) is present."""
    user = await _active_user_from_cookie(request, session)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    return user


AdminDep = Annotated[None, Depends(require_any_admin)]
UserDep = Annotated[User, Depends(get_current_user)]


async def get_draft_or_404(draft_id: uuid.UUID, session: SessionDep) -> Draft:
    draft = await session.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Draft {draft_id} not found")
    return draft


DraftDep = Annotated[Draft, Depends(get_draft_or_404)]
