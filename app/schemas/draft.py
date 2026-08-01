import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DraftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    mime_type: str
    parse_status: str
    parse_error: str | None
    language_code: str
    created_at: datetime
    parsed_at: datetime | None


class DraftDetail(DraftRead):
    raw_text: str | None
    parsed_content: dict | None
