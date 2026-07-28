"""Placeholder — implemented in M6."""
import uuid

from sqlalchemy.orm import Session


def parse_and_store_draft(session: Session, draft_id: uuid.UUID) -> dict:
    return {"blocks": 0, "sentences": 0}
