"""Shared contract for enrichment providers."""

from typing import Protocol

from pydantic import BaseModel, Field

from app.db.models.enums import EnrichmentProvider


class RefIdentity(BaseModel):
    """Everything a provider may use to look a paper up."""

    title: str
    doi: str | None = None
    scopus_eid: str | None = None
    semantic_scholar_id: str | None = None
    source_link: str | None = None


class EnrichmentResult(BaseModel):
    provider: EnrichmentProvider
    title: str | None = None
    abstract: str | None = None
    authors: list[dict] = Field(default_factory=list)
    year: int | None = None
    source_title: str | None = None
    doi: str | None = None
    scopus_eid: str | None = None
    scopus_id: str | None = None
    semantic_scholar_id: str | None = None
    author_keywords: list[str] = Field(default_factory=list)
    index_keywords: list[str] = Field(default_factory=list)
    subject_areas: list[str] = Field(default_factory=list)
    citation_count: int | None = None
    document_type: str | None = None
    publisher_url: str | None = None
    scopus_url: str | None = None

    @property
    def has_abstract(self) -> bool:
        return bool(self.abstract and self.abstract.strip())


class ProviderAuthError(RuntimeError):
    """Credentials rejected — disable this provider for the rest of the run."""


class RateLimited(RuntimeError):
    def __init__(self, retry_after: float | None = None):
        super().__init__(f"rate limited (retry_after={retry_after})")
        self.retry_after = retry_after


class EnrichmentProviderClient(Protocol):
    name: str

    def fetch(self, ref: RefIdentity) -> EnrichmentResult | None:
        """Return metadata, or None when the record simply isn't found."""
        ...
