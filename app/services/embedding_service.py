"""Placeholder — implemented in M5."""
import uuid

from sqlalchemy.orm import Session


def embed_project_references(session: Session, project_id: uuid.UUID) -> dict:
    return {"embedded": 0, "skipped": 0}
