"""Public API: `run_export` is the one entry point routes should call.

Export is synchronous, not a Celery task -- opening and stitching a
~30-page docx takes tens of milliseconds, and the worker process runs
`--pool=solo` for MPS, so an export queued behind a multi-minute analysis
stage would feel broken for no reason. If a future document proves this
wrong, `build_bundle` + the per-format writers already do all the real
work, so moving to a task is a one-function change.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Export
from app.db.models.enums import ExportFormat
from app.services.export.bundle import build_bundle
from app.services.export.docx_writer import write_docx
from app.services.export.markdown_writer import write_markdown
from app.services.export.tabular_writer import write_csv, write_json


class UnsupportedExportError(ValueError):
    pass


@dataclass(frozen=True)
class GeneratedExport:
    content: bytes
    extension: str
    inserted_count: int
    mismatch_count: int
    outcomes: list[dict]


def _generate(
    session: Session,
    draft_id: uuid.UUID,
    *,
    format: str,
    citation_style: str,
    insertion_mode: str,
    include_audit_report: bool,
) -> GeneratedExport:
    bundle = build_bundle(session, draft_id, style=citation_style)

    if format == ExportFormat.DOCX:
        docx_bytes, outcomes = write_docx(
            bundle, mode=insertion_mode, include_audit_report=include_audit_report
        )
        outcome_dicts = [
            {
                "claim_id": str(o.claim_id),
                "status": o.status,
                "citation_text": o.citation_text,
                "paragraph_index": o.paragraph_index,
            }
            for o in outcomes
        ]
        return GeneratedExport(
            content=docx_bytes,
            extension="docx",
            inserted_count=sum(1 for o in outcomes if o.status == "INSERTED"),
            mismatch_count=sum(1 for o in outcomes if o.status == "POSITION_MISMATCH"),
            outcomes=outcome_dicts,
        )

    if format == ExportFormat.MD:
        body, outcomes = write_markdown(bundle, include_audit_report=include_audit_report)
        outcome_dicts = [
            {"claim_id": str(o.claim_id), "status": o.status, "citation_text": o.citation_text}
            for o in outcomes
        ]
        return GeneratedExport(
            content=body.encode("utf-8"),
            extension="md",
            inserted_count=sum(1 for o in outcomes if o.status == "INSERTED"),
            mismatch_count=sum(1 for o in outcomes if o.status == "POSITION_MISMATCH"),
            outcomes=outcome_dicts,
        )

    if format == ExportFormat.CSV:
        content = write_csv(bundle)
        return GeneratedExport(
            content=content.encode("utf-8"), extension="csv", inserted_count=0,
            mismatch_count=0, outcomes=[],
        )

    if format == ExportFormat.JSON:
        content = write_json(
            bundle, citation_style=citation_style, insertion_mode=insertion_mode
        )
        return GeneratedExport(
            content=content.encode("utf-8"), extension="json", inserted_count=0,
            mismatch_count=0, outcomes=[],
        )

    raise UnsupportedExportError(f"Unknown export format: {format!r}")


def run_export(
    session: Session,
    draft_id: uuid.UUID,
    *,
    format: str,
    citation_style: str = "APA",
    insertion_mode: str = "tracked_changes",
    include_audit_report: bool = True,
) -> Export:
    generated = _generate(
        session,
        draft_id,
        format=format,
        citation_style=citation_style,
        insertion_mode=insertion_mode,
        include_audit_report=include_audit_report,
    )

    export_id = uuid.uuid4()
    directory = get_settings().upload_dir / "exports" / str(export_id)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"export_{export_id}.{generated.extension}"
    storage_path = directory / filename
    storage_path.write_bytes(generated.content)

    export = Export(
        id=export_id,
        draft_id=draft_id,
        format=format,
        citation_style=citation_style,
        insertion_mode=insertion_mode,
        include_audit_report=include_audit_report,
        storage_path=str(storage_path),
        filename=filename,
        byte_size=len(generated.content),
        inserted_count=generated.inserted_count,
        mismatch_count=generated.mismatch_count,
        outcomes=generated.outcomes,
    )
    session.add(export)
    session.commit()
    session.refresh(export)
    return export
