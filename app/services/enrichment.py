"""Enrichment orchestration: provider chain + the reference-updating stage.

Chain order is Scopus (authoritative) -> Semantic Scholar -> Crossref.
The first provider that returns an abstract wins and the reference is
ENRICHED. Crossref can only contribute bibliographic metadata, so a row
that gets no further than Crossref stays INCOMPLETE — the recommendation
engine then treats it as INSUFFICIENT_EVIDENCE rather than guessing.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import ReferencePaper
from app.db.models.enums import EnrichmentProvider, EnrichmentStatus
from app.services.enrichment_types import (
    EnrichmentProviderClient,
    EnrichmentResult,
    RefIdentity,
)

log = get_logger(__name__)

#: Rows per transaction during enrichment.
COMMIT_EVERY = 50


def get_enrichment_chain() -> list[EnrichmentProviderClient]:
    settings = get_settings()
    if settings.scopus_mocked:
        from app.services.mocks.mock_scopus import MockScopusService

        # Offline mode: the mock fills the Scopus slot and the network-only
        # fallbacks are omitted so tests never reach the internet.
        return [MockScopusService()]

    from app.services.crossref_service import CrossrefService
    from app.services.scopus_service import ScopusService
    from app.services.semantic_scholar_service import SemanticScholarService

    return [ScopusService(), SemanticScholarService(), CrossrefService()]


def _identity(reference: ReferencePaper) -> RefIdentity:
    return RefIdentity(
        title=reference.title,
        doi=reference.doi,
        scopus_eid=reference.scopus_eid,
        semantic_scholar_id=reference.semantic_scholar_id,
        source_link=reference.source_link,
    )


def apply_result(reference: ReferencePaper, result: EnrichmentResult) -> None:
    """Fill blanks from a provider result; never overwrite dataset values."""
    if result.abstract and not reference.abstract:
        reference.abstract = result.abstract.strip()
    if result.authors and not reference.authors:
        reference.authors = result.authors
    if result.year and not reference.year:
        reference.year = result.year
    if result.source_title and not reference.source_title:
        reference.source_title = result.source_title
    if result.doi and not reference.doi:
        reference.doi = result.doi
    if result.scopus_eid and not reference.scopus_eid:
        reference.scopus_eid = result.scopus_eid
    if result.scopus_id and not reference.scopus_id:
        reference.scopus_id = result.scopus_id
    if result.semantic_scholar_id and not reference.semantic_scholar_id:
        reference.semantic_scholar_id = result.semantic_scholar_id
    if result.author_keywords and not reference.author_keywords:
        reference.author_keywords = result.author_keywords
    if result.index_keywords and not reference.index_keywords:
        reference.index_keywords = result.index_keywords
    if result.subject_areas and not reference.subject_areas:
        reference.subject_areas = result.subject_areas
    if result.citation_count is not None and reference.citation_count is None:
        reference.citation_count = result.citation_count
    if result.document_type and not reference.document_type:
        reference.document_type = result.document_type
    if result.scopus_url and not reference.scopus_url:
        reference.scopus_url = result.scopus_url
    if result.publisher_url and not reference.publisher_url:
        reference.publisher_url = result.publisher_url


def enrich_reference(reference: ReferencePaper, chain: list[EnrichmentProviderClient]) -> None:
    identity = _identity(reference)
    providers_tried: list[str] = []

    for provider in chain:
        if not getattr(provider, "supplies_abstracts", True) and reference.year and reference.source_title:
            # This provider cannot contribute an abstract and the row already
            # has the metadata it could offer. Skipping saves a request per row,
            # which on a multi-thousand-row dataset is the difference between
            # minutes and hours.
            continue
        try:
            result = provider.fetch(identity)
        except Exception as exc:
            log.warning(
                "provider_failed",
                provider=provider.name,
                reference_id=str(reference.id),
                error=str(exc),
            )
            providers_tried.append(f"{provider.name}:error")
            continue

        providers_tried.append(provider.name)
        if result is None:
            continue

        apply_result(reference, result)
        if reference.abstract:
            reference.enrichment_status = EnrichmentStatus.ENRICHED
            reference.enrichment_provider = result.provider
            reference.enrichment_error = None
            reference.enriched_at = datetime.now(UTC)
            return

    reference.enrichment_status = EnrichmentStatus.INCOMPLETE
    reference.enrichment_provider = reference.enrichment_provider or EnrichmentProvider.NONE
    reference.enrichment_error = (
        f"No abstract retrieved (tried: {', '.join(providers_tried) or 'none'})"
    )
    reference.enriched_at = datetime.now(UTC)


def enrich_project_references(session: Session, project_id: uuid.UUID) -> dict:
    """Stage body: enrich every PENDING reference in the project.

    Idempotent — rows already ENRICHED/INCOMPLETE are skipped, so re-running
    an analysis only picks up newly imported references.
    """
    pending = list(
        session.execute(
            select(ReferencePaper)
            .where(
                ReferencePaper.project_id == project_id,
                ReferencePaper.enrichment_status == EnrichmentStatus.PENDING,
            )
            .order_by(ReferencePaper.original_row_number)
        ).scalars()
    )
    if not pending:
        return {"enriched": 0, "incomplete": 0, "failed": 0}

    chain = get_enrichment_chain()
    counts = {"enriched": 0, "incomplete": 0, "failed": 0}
    processed = 0
    try:
        # Providers that can resolve many records per request do so up front.
        identities = [_identity(r) for r in pending]
        for provider in chain:
            prefetch = getattr(provider, "prefetch", None)
            if prefetch:
                prefetch(identities)

        for reference in pending:
            try:
                enrich_reference(reference, chain)
            except Exception as exc:
                reference.enrichment_status = EnrichmentStatus.FAILED
                reference.enrichment_error = f"{type(exc).__name__}: {exc}"
                reference.enriched_at = datetime.now(UTC)
                log.error("enrichment_failed", reference_id=str(reference.id), error=str(exc))

            if reference.enrichment_status == EnrichmentStatus.ENRICHED:
                counts["enriched"] += 1
            elif reference.enrichment_status == EnrichmentStatus.INCOMPLETE:
                counts["incomplete"] += 1
            else:
                counts["failed"] += 1

            # Commit in batches: frequent enough that /analysis/status shows
            # live progress, infrequent enough not to dominate the runtime.
            processed += 1
            if processed % COMMIT_EVERY == 0:
                session.commit()
                log.info("enrichment_progress", done=processed, total=len(pending), **counts)
        session.commit()
    finally:
        for provider in chain:
            close = getattr(provider, "close", None)
            if close:
                close()

    return counts
