import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImportResult(BaseModel):
    imported: int
    skipped_duplicates: int
    skipped_invalid: int
    backfilled_abstracts: int
    warnings: list[str]


class MissingAbstractsByYear(BaseModel):
    year: int | None
    missing: int
    total: int


class ReferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    abstract: str | None
    authors: list | None
    year: int | None
    source_title: str | None
    field_of_study: str | None
    doi: str | None
    scopus_eid: str | None
    author_keywords: list[str] | None
    index_keywords: list[str] | None
    source_link: str | None
    citation_count: int | None
    enrichment_status: str
    enrichment_provider: str | None
    enrichment_error: str | None
    enriched_at: datetime | None
