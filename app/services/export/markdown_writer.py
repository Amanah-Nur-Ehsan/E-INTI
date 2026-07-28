"""Markdown export: the one format that works for every draft type
(.docx, .md, .txt all produce the same `raw_text` + `blocks` shape), so
this is what a .docx-only feature (like tracked changes) falls back to.

Uses the same descending-order, resolve-before-mutate discipline as the
DOCX writer, but on a plain string instead of oxml -- each block's citation
splices are computed against the pristine block text before any of that
block's insertions are applied, and processed highest-offset-first.
"""

from dataclasses import dataclass

from app.services.citation_formatting_service import join_in_text
from app.services.export.bundle import ExportBundle
from app.services.export.docx_ops import find_insertion_offset


@dataclass(frozen=True)
class MarkdownInsertionOutcome:
    claim_id: object
    status: str  # "INSERTED" | "POSITION_MISMATCH" | "EMPTY_CITATION"
    citation_text: str | None


def write_markdown(
    bundle: ExportBundle, include_audit_report: bool = False
) -> tuple[str, list[MarkdownInsertionOutcome]]:
    outcomes: list[MarkdownInsertionOutcome] = []

    items_by_paragraph: dict[int, list] = {}
    for item in bundle.accepted:
        items_by_paragraph.setdefault(item.claim.paragraph_index, []).append(item)

    rendered_blocks: list[str] = []
    for block in bundle.blocks:
        text = block.text
        items = items_by_paragraph.get(block.paragraph_index, [])
        items = sorted(items, key=lambda i: i.claim.char_start or 0, reverse=True)

        for item in items:
            citations = [bundle.context.in_text(ref.id) for ref in item.references]
            joined = join_in_text(citations)
            if not joined:
                outcomes.append(
                    MarkdownInsertionOutcome(
                        claim_id=item.claim.id, status="EMPTY_CITATION", citation_text=None
                    )
                )
                continue

            s0 = (item.claim.char_start or 0) - block.char_start
            s1 = (item.claim.char_end or 0) - block.char_start
            if not (0 <= s0 <= s1 <= len(block.text)):
                outcomes.append(
                    MarkdownInsertionOutcome(
                        claim_id=item.claim.id, status="POSITION_MISMATCH", citation_text=joined
                    )
                )
                continue
            if block.text[s0:s1] != item.claim.sentence_text:
                outcomes.append(
                    MarkdownInsertionOutcome(
                        claim_id=item.claim.id, status="POSITION_MISMATCH", citation_text=joined
                    )
                )
                continue

            insert_at = find_insertion_offset(text, s0, s1)
            text = f"{text[:insert_at]} {joined}{text[insert_at:]}"
            outcomes.append(
                MarkdownInsertionOutcome(
                    claim_id=item.claim.id, status="INSERTED", citation_text=joined
                )
            )

        if block.is_heading:
            prefix = "# " if block.paragraph_index == bundle.blocks[0].paragraph_index else "## "
            rendered_blocks.append(f"{prefix}{text}")
        else:
            rendered_blocks.append(text)

    body = "\n\n".join(rendered_blocks)

    bibliography = bundle.context.bibliography()
    if bibliography:
        entries = "\n".join(
            "- " + "".join(f"*{seg.text}*" if seg.italic else seg.text for seg in segments)
            for _reference_id, segments in bibliography
        )
        body = f"{body}\n\n## References\n\n{entries}"

    if include_audit_report:
        body = f"{body}\n\n{_render_audit_table(bundle)}"

    return body, outcomes


def _render_audit_table(bundle: ExportBundle) -> str:
    from app.services.export.audit import build_audit_rows

    rows = build_audit_rows(bundle)
    if not rows:
        return "## Citation Audit Report\n\n_No claims required a citation._"

    header = "| Section | Claim | Type | Existing citation | Score | Verdict | Decision | Status |"
    separator = "|---|---|---|---|---|---|---|---|"
    lines = [header, separator]
    for row in rows:
        score = f"{row.score_percentage:.1f}%" if row.score_percentage is not None else ""
        claim = (row.claim_text or "").replace("|", "\\|")[:120]
        lines.append(
            f"| {row.section_title or ''} | {claim} | {row.claim_type or ''} | "
            f"{row.existing_citation_status} | {score} | {row.verdict or ''} | "
            f"{row.user_decision} | {row.insertion_status} |"
        )
    return "## Citation Audit Report\n\n" + "\n".join(lines)
