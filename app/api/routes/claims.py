from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DraftDep, SessionDep
from app.db.models import Claim
from app.schemas.claim import ClaimRead

router = APIRouter(tags=["claims"])


@router.get("/drafts/{draft_id}/claims", response_model=list[ClaimRead])
async def list_claims(
    draft: DraftDep,
    session: SessionDep,
    needs_citation: bool | None = Query(default=None),
    existing_citation_status: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    limit: int = Query(default=500, le=2000),
    offset: int = Query(default=0, ge=0),
) -> list[Claim]:
    stmt = select(Claim).where(Claim.draft_id == draft.id)
    if needs_citation is not None:
        stmt = stmt.where(Claim.needs_citation.is_(needs_citation))
    if existing_citation_status:
        stmt = stmt.where(Claim.existing_citation_status == existing_citation_status)
    if review_status:
        stmt = stmt.where(Claim.review_status == review_status)
    stmt = stmt.order_by(Claim.char_start).limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars())
