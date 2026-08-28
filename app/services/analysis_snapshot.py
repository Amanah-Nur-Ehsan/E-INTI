import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AcceptedCitation,
    AnalysisRun,
    CitationRecommendation,
    Claim,
    Draft,
    ReferencePaper,
)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _ref_dict(ref: ReferencePaper) -> dict:
    return {
        "title": ref.title,
        "authors": ref.authors,
        "year": ref.year,
        "source": ref.source_title,
        "doi": ref.doi,
        "scopus_url": ref.scopus_url,
        "citation_count": ref.citation_count,
    }


def build_run_snapshot(session: Session, run_id: uuid.UUID) -> dict:
    """Serialize a completed run's full result (draft text, SDG, every claim
    with its recommendations, accepted citations) into a JSON-ready dict so
    the History screen can show a frozen copy of the analysis."""
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise ValueError(f"AnalysisRun {run_id} not found")
    draft = session.get(Draft, run.draft_id)

    claims = list(
        session.execute(
            select(Claim)
            .where(Claim.draft_id == draft.id)
            .order_by(Claim.paragraph_index, Claim.sentence_index)
        )
        .scalars()
    )

    recs_by_claim: dict[uuid.UUID, list[dict]] = {}
    if claims:
        rows = session.execute(
            select(CitationRecommendation, ReferencePaper)
            .join(ReferencePaper, CitationRecommendation.reference_id == ReferencePaper.id)
            .where(CitationRecommendation.claim_id.in_([c.id for c in claims]))
            .order_by(CitationRecommendation.claim_id, CitationRecommendation.rank)
        ).all()
        for rec, ref in rows:
            recs_by_claim.setdefault(rec.claim_id, []).append(
                {
                    "id": str(rec.id),
                    "rank": rec.rank,
                    "score": rec.score_percentage,
                    "label": rec.recommendation_label,
                    "verdict": rec.verdict,
                    "usage": rec.recommended_usage,
                    "evidence": rec.evidence_paraphrase,
                    "limitations": rec.limitations,
                    "decision": rec.user_decision,
                    "note": rec.user_note,
                    "reference": _ref_dict(ref),
                }
            )

    accepted = session.execute(
        select(AcceptedCitation, ReferencePaper)
        .join(ReferencePaper, AcceptedCitation.reference_id == ReferencePaper.id)
        .where(AcceptedCitation.claim_id.in_([c.id for c in claims]))
    ).all()

    claims_list = []
    needs_citation = 0
    for c in claims:
        if c.needs_citation:
            needs_citation += 1
        claims_list.append(
            {
                "id": str(c.id),
                "sentence": c.sentence_text,
                "claim_text": c.claim_text,
                "claim_type": c.claim_type,
                "needs_citation": c.needs_citation,
                "section": c.section_title,
                "recommendations": recs_by_claim.get(c.id, []),
            }
        )

    return {
        "run": {
            "id": str(run.id),
            "status": run.status,
            "stage": run.stage,
            "error": run.error,
            "started_at": _iso(run.started_at),
            "finished_at": _iso(run.finished_at),
            "created_at": _iso(run.created_at),
        },
        "draft": {
            "id": str(draft.id),
            "filename": draft.original_filename,
            "mime_type": draft.mime_type,
            "language_code": draft.language_code,
            "raw_text": draft.raw_text,
            "created_at": _iso(draft.created_at),
        },
        "sdg": {
            "number": draft.sdg_number,
            "name": draft.sdg_name,
            "keyword": draft.sdg_keyword,
            "rationale": draft.sdg_rationale,
            "closest_number": draft.sdg_closest_number,
            "closest_name": draft.sdg_closest_name,
        },
        "summary": {
            "claims_total": len(claims_list),
            "claims_needing_citation": needs_citation,
            "recommendations": sum(len(r["recommendations"]) for r in claims_list),
            "accepted": len(accepted),
        },
        "claims": claims_list,
        "accepted_citations": [
            {
                "claim_id": str(a.claim_id),
                "citation_text": a.citation_text,
                "reference": _ref_dict(ref),
            }
            for a, ref in accepted
        ],
    }
