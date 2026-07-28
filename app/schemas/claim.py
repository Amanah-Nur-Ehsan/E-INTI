import uuid

from pydantic import BaseModel, ConfigDict


class ClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    draft_id: uuid.UUID
    section_title: str | None
    paragraph_index: int | None
    sentence_index: int | None
    char_start: int | None
    char_end: int | None
    sentence_text: str
    local_context: str
    claim_text: str | None
    needs_citation: bool
    claim_type: str | None
    claim_confidence: float | None
    detection_method: str | None
    existing_citation_text: str | None
    existing_citation_status: str
    review_status: str
    keywords: list | None
