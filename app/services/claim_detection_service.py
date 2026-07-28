"""Placeholder — implemented in M7."""
import uuid

from sqlalchemy.orm import Session


def detect_and_store_claims(session: Session, draft_id: uuid.UUID) -> dict:
    return {"claims": 0, "needs_citation": 0}
