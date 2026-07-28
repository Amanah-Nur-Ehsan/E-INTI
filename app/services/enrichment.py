"""Placeholder — implemented in M4."""
import uuid

from sqlalchemy.orm import Session


def enrich_project_references(session: Session, project_id: uuid.UUID) -> dict:
    return {"enriched": 0, "incomplete": 0, "skipped": 0}
