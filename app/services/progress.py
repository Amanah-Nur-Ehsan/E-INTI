"""Live pipeline progress, derived from row counts.

Counters are never stored — they would drift whenever a stage is re-run
or a row is edited outside the pipeline.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AcceptedCitation, CitationRecommendation, Claim, ReferencePaper
from app.db.models.enums import EnrichmentStatus
from app.schemas.analysis import ClaimCounts, ReferenceCounts


async def reference_counts(session: AsyncSession) -> ReferenceCounts:
    rows = (
        await session.execute(
            select(ReferencePaper.enrichment_status, func.count()).group_by(
                ReferencePaper.enrichment_status
            )
        )
    ).all()
    by_status = {status: count for status, count in rows}

    embedded = (
        await session.execute(
            select(func.count())
            .select_from(ReferencePaper)
            .where(ReferencePaper.embedding.isnot(None))
        )
    ).scalar_one()

    missing_abstract = (
        await session.execute(
            select(func.count())
            .select_from(ReferencePaper)
            .where(ReferencePaper.abstract.is_(None))
        )
    ).scalar_one()

    embed_pending = (
        await session.execute(
            select(func.count())
            .select_from(ReferencePaper)
            .where(
                ReferencePaper.abstract.isnot(None),
                ReferencePaper.content_hash.is_(None),
            )
        )
    ).scalar_one()

    return ReferenceCounts(
        total=sum(by_status.values()),
        pending=by_status.get(EnrichmentStatus.PENDING, 0),
        enriched=by_status.get(EnrichmentStatus.ENRICHED, 0),
        incomplete=by_status.get(EnrichmentStatus.INCOMPLETE, 0),
        failed=by_status.get(EnrichmentStatus.FAILED, 0),
        missing_abstract=missing_abstract,
        embed_pending=embed_pending,
        embedded=embedded,
    )


async def claim_counts(session: AsyncSession, draft_id: uuid.UUID) -> ClaimCounts:
    total = (
        await session.execute(
            select(func.count()).select_from(Claim).where(Claim.draft_id == draft_id)
        )
    ).scalar_one()
    needs = (
        await session.execute(
            select(func.count())
            .select_from(Claim)
            .where(Claim.draft_id == draft_id, Claim.needs_citation.is_(True))
        )
    ).scalar_one()
    with_recs = (
        await session.execute(
            select(func.count(func.distinct(CitationRecommendation.claim_id)))
            .select_from(CitationRecommendation)
            .join(Claim, Claim.id == CitationRecommendation.claim_id)
            .where(Claim.draft_id == draft_id)
        )
    ).scalar_one()

    return ClaimCounts(total=total, needs_citation=needs, with_recommendations=with_recs)


async def accepted_citation_counts(session: AsyncSession, draft_id: uuid.UUID) -> tuple[int, int]:
    """Returns (total accepted citation rows, distinct claims with >=1 accepted).

    A claim can have more than one accepted reference, so these two counts
    diverge -- the dashboard's coverage percentage needs the second one.
    """
    total = (
        await session.execute(
            select(func.count())
            .select_from(AcceptedCitation)
            .join(Claim, Claim.id == AcceptedCitation.claim_id)
            .where(Claim.draft_id == draft_id)
        )
    ).scalar_one()
    distinct_claims = (
        await session.execute(
            select(func.count(func.distinct(AcceptedCitation.claim_id)))
            .select_from(AcceptedCitation)
            .join(Claim, Claim.id == AcceptedCitation.claim_id)
            .where(Claim.draft_id == draft_id)
        )
    ).scalar_one()
    return total, distinct_claims
