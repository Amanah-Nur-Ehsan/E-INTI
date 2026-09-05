import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import SessionDep, require_any_admin
from app.core.security import _user_session_user_id, hash_password, revoke_user_sessions
from app.db.models import User
from app.schemas.admin_users import (
    ResetPasswordAdminRequest,
    UpdateUserAdminRequest,
    UserAdminRead,
)

router = APIRouter(
    prefix="/admin/users", tags=["admin"], dependencies=[Depends(require_any_admin)]
)


@router.get("", response_model=list[UserAdminRead])
async def list_users(session: SessionDep) -> list[User]:
    return list((await session.scalars(select(User).order_by(User.created_at))).all())


async def _get_user_or_404(session: SessionDep, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


@router.patch("/{user_id}", response_model=UserAdminRead)
async def update_user(
    user_id: uuid.UUID, body: UpdateUserAdminRequest, session: SessionDep, request: Request
) -> User:
    user = await _get_user_or_404(session, user_id)
    me = await _user_session_user_id(request)
    is_self = me == str(user.id)

    if body.full_name is not None:
        user.full_name = body.full_name.strip() or None
    if body.phone is not None:
        user.phone = body.phone.strip() or None
    if body.address is not None:
        user.address = body.address.strip() or None
    if body.affiliation is not None:
        user.affiliation = body.affiliation.strip() or None
    if body.bio is not None:
        user.bio = body.bio.strip() or None

    if body.email is not None:
        new_email = body.email.lower()
        if new_email != user.email:
            existing = await session.scalar(
                select(User).where(User.email == new_email, User.id != user.id)
            )
            if existing is not None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "A user with this email already exists"
                )
            user.email = new_email

    if body.role is not None:
        if is_self:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot change your own role")
        user.role = body.role

    if body.is_active is not None:
        if is_self and not body.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate your own account")
        user.is_active = body.is_active
        if not body.is_active:
            await revoke_user_sessions(str(user.id))

    await session.commit()
    return user


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_password(
    user_id: uuid.UUID, body: ResetPasswordAdminRequest, session: SessionDep
) -> None:
    user = await _get_user_or_404(session, user_id)
    user.password_hash = hash_password(body.new_password)
    await revoke_user_sessions(str(user.id))
    await session.commit()


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: uuid.UUID, session: SessionDep, request: Request) -> None:
    me = await _user_session_user_id(request)
    if me == str(user_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete your own account")
    user = await _get_user_or_404(session, user_id)
    await revoke_user_sessions(str(user.id))
    await session.delete(user)
    await session.commit()
