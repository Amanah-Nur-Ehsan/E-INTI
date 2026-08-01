"""Gathers everything an export needs into one immutable snapshot.

One query, taken once at the start of an export, so the writer never has
to reach back into the session — and so a claim's accepted references are
grouped and ordered consistently across every output format (docx, md,
csv, json all read from the same `ExportBundle`).
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AcceptedCitation,
    CitationRecommendation,
    Claim,
    Draft,
    ReferencePaper,
)
from app.services.citation_formatting_service import CitationContext, build_citation_context
from app.services.draft_parser_service import Block


@dataclass(frozen=True)
class AcceptedItem:
    """One claim and the references accepted for it, in acceptance order.

    `recommendations[i]` is the CitationRecommendation that scored
    `references[i]` for this claim, when the acceptance traces back to one
    (it always should, but AcceptedCitation.recommendation_id is nullable
    against a SET NULL FK, so a None is tolerated rather than assumed away).
    """

    claim: Claim
    references: list[ReferencePaper] = field(default_factory=list)
    recommendations: list[CitationRecommendation | None] = field(default_factory=list)


@dataclass(frozen=True)
class ExportBundle:
    draft: Draft
    blocks: list[Block]
    accepted: list[AcceptedItem]  # ordered by claim.char_start
    all_claims: list[Claim]  # every claim, for the audit report (6d)
    context: CitationContext


class DraftNotParsedError(ValueError):
    pass


def _rehydrate_blocks(draft: Draft) -> list[Block]:
    if not draft.parsed_content:
        raise DraftNotParsedError(f"Draft {draft.id} has no parsed_content; run analysis first")
    return [Block(**b) for b in draft.parsed_content.get("blocks", [])]


def build_bundle(session: Session, draft_id: uuid.UUID, style: str = "APA") -> ExportBundle:
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise ValueError(f"Draft {draft_id} not found")

    blocks = _rehydrate_blocks(draft)

    all_claims = list(
        session.execute(
            select(Claim).where(Claim.draft_id == draft_id).order_by(Claim.char_start)
        ).scalars()
    )

    accepted_rows = session.execute(
        select(AcceptedCitation, ReferencePaper, CitationRecommendation)
        .join(ReferencePaper, ReferencePaper.id == AcceptedCitation.reference_id)
        .join(Claim, Claim.id == AcceptedCitation.claim_id)
        .outerjoin(
            CitationRecommendation, CitationRecommendation.id == AcceptedCitation.recommendation_id
        )
        .where(Claim.draft_id == draft_id)
        .order_by(AcceptedCitation.created_at)
    ).all()

    refs_by_claim_id: dict[uuid.UUID, list[ReferencePaper]] = {}
    recs_by_claim_id: dict[uuid.UUID, list[CitationRecommendation | None]] = {}
    claims_by_id = {c.id: c for c in all_claims}
    for accepted, ref, recommendation in accepted_rows:
        refs_by_claim_id.setdefault(accepted.claim_id, []).append(ref)
        recs_by_claim_id.setdefault(accepted.claim_id, []).append(recommendation)

    # Dedupe by reference id before building the context: the same paper is
    # commonly accepted for more than one claim, and CitationContext would
    # otherwise emit one bibliography entry per (claim, reference) pair
    # instead of one per unique reference.
    unique_refs: dict[uuid.UUID, ReferencePaper] = {}
    for refs in refs_by_claim_id.values():
        for ref in refs:
            unique_refs.setdefault(ref.id, ref)
    context = build_citation_context(list(unique_refs.values()), style=style)

    accepted_items = [
        AcceptedItem(
            claim=claims_by_id[claim_id],
            references=refs,
            recommendations=recs_by_claim_id.get(claim_id, [None] * len(refs)),
        )
        for claim_id, refs in refs_by_claim_id.items()
        if claim_id in claims_by_id
    ]
    accepted_items.sort(key=lambda item: item.claim.char_start or 0)

    return ExportBundle(
        draft=draft,
        blocks=blocks,
        accepted=accepted_items,
        all_claims=all_claims,
        context=context,
    )
