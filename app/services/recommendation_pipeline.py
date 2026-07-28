"""Placeholder — implemented in M8."""
import uuid

from sqlalchemy.orm import Session


def recommend_for_draft(session: Session, project_id: uuid.UUID, draft_id: uuid.UUID) -> dict:
    return {"claims_processed": 0, "recommendations": 0}
