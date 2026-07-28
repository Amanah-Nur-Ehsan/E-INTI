"""The citation audit report: one row per claim that needed a citation,
shared across every export format so .docx's appended table, .md's
table, and .csv/.json (which *are* the audit report) never disagree.

Position validation here is deliberately the cheap version — a direct
slice against `draft.raw_text` — rather than the paragraph/run-aware
check `docx_ops.resolve_insertion_point` performs. It is what the
markdown writer's splice needs, and it is enough to report drift for
tabular formats that never touch a docx: a raw_text mismatch is the
same underlying fact (the draft changed since analysis) regardless of
which format is asking.
"""

from dataclasses import dataclass

from app.services.citation_formatting_service import join_in_text
from app.services.export.bundle import AcceptedItem, ExportBundle

POSITION_MISMATCH = "POSITION_MISMATCH"
INSERTED = "INSERTED"
NOT_ACCEPTED = "NOT_ACCEPTED"


@dataclass(frozen=True)
class AuditRow:
    section_title: str | None
    paragraph_index: int | None
    claim_text: str
    claim_type: str | None
    existing_citation_status: str
    citation_text: str | None
    reference_titles: str | None
    reference_years: str | None
    reference_links: str | None
    score_percentage: float | None
    verdict: str | None
    recommendation_label: str | None
    user_decision: str
    user_note: str | None
    insertion_status: str


def check_raw_text_position(bundle: ExportBundle, item: AcceptedItem) -> bool:
    """True if the claim's stored offsets still slice out its own sentence
    text from the draft's current raw_text -- i.e. nothing has drifted.
    """
    raw_text = bundle.draft.raw_text or ""
    start, end = item.claim.char_start, item.claim.char_end
    if start is None or end is None or not (0 <= start <= end <= len(raw_text)):
        return False
    return raw_text[start:end] == item.claim.sentence_text


def _reference_link(reference) -> str | None:
    if reference.doi:
        return f"https://doi.org/{reference.doi}"
    return reference.scopus_url or reference.source_link


def build_audit_rows(bundle: ExportBundle) -> list[AuditRow]:
    accepted_by_claim = {item.claim.id: item for item in bundle.accepted}
    rows: list[AuditRow] = []

    for claim in bundle.all_claims:
        if not claim.needs_citation:
            continue

        item = accepted_by_claim.get(claim.id)
        if item is None:
            rows.append(
                AuditRow(
                    section_title=claim.section_title,
                    paragraph_index=claim.paragraph_index,
                    claim_text=claim.claim_text or claim.sentence_text,
                    claim_type=claim.claim_type,
                    existing_citation_status=claim.existing_citation_status,
                    citation_text=None,
                    reference_titles=None,
                    reference_years=None,
                    reference_links=None,
                    score_percentage=None,
                    verdict=None,
                    recommendation_label=None,
                    user_decision="PENDING",
                    user_note=None,
                    insertion_status=NOT_ACCEPTED,
                )
            )
            continue

        position_ok = check_raw_text_position(bundle, item)
        citations = [bundle.context.in_text(ref.id) for ref in item.references]
        recommendation = next((r for r in item.recommendations if r is not None), None)

        rows.append(
            AuditRow(
                section_title=claim.section_title,
                paragraph_index=claim.paragraph_index,
                claim_text=claim.claim_text or claim.sentence_text,
                claim_type=claim.claim_type,
                existing_citation_status=claim.existing_citation_status,
                citation_text=join_in_text(citations),
                reference_titles="; ".join(ref.title for ref in item.references),
                reference_years="; ".join(str(ref.year or "n.d.") for ref in item.references),
                reference_links="; ".join(filter(None, (_reference_link(r) for r in item.references))),
                score_percentage=recommendation.score_percentage if recommendation else None,
                verdict=recommendation.verdict if recommendation else None,
                recommendation_label=(
                    recommendation.recommendation_label if recommendation else None
                ),
                user_decision=recommendation.user_decision if recommendation else "ACCEPTED",
                user_note=recommendation.user_note if recommendation else None,
                insertion_status=INSERTED if position_ok else POSITION_MISMATCH,
            )
        )

    return rows


AUDIT_FIELDNAMES = [
    "section_title",
    "paragraph_index",
    "claim_text",
    "claim_type",
    "existing_citation_status",
    "citation_text",
    "reference_titles",
    "reference_years",
    "reference_links",
    "score_percentage",
    "verdict",
    "recommendation_label",
    "user_decision",
    "user_note",
    "insertion_status",
]


def audit_row_as_dict(row: AuditRow) -> dict:
    return {name: getattr(row, name) for name in AUDIT_FIELDNAMES}
