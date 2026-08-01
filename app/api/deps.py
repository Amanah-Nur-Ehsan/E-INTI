import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Draft
from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_draft_or_404(draft_id: uuid.UUID, session: SessionDep) -> Draft:
    draft = await session.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Draft {draft_id} not found")
    return draft


DraftDep = Annotated[Draft, Depends(get_draft_or_404)]
