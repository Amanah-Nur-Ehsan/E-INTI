"""CSV and JSON exports -- these two formats *are* the audit report,
rather than a document with the audit report appended.
"""

import csv
import json
from datetime import UTC, datetime
from io import StringIO

from app.services.export.audit import AUDIT_FIELDNAMES, audit_row_as_dict, build_audit_rows
from app.services.export.bundle import ExportBundle


def write_csv(bundle: ExportBundle) -> str:
    rows = build_audit_rows(bundle)
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=AUDIT_FIELDNAMES)
    writer.writeheader()
    for row in rows:
        writer.writerow(audit_row_as_dict(row))
    return buffer.getvalue()


def write_json(bundle: ExportBundle, *, citation_style: str = "APA", insertion_mode: str = "n/a") -> str:
    rows = build_audit_rows(bundle)

    bibliography = [
        {
            "reference_id": str(reference_id),
            "text": "".join(seg.text for seg in segments),
        }
        for reference_id, segments in bundle.context.bibliography()
    ]

    accepted = [
        {
            "claim_id": str(item.claim.id),
            "sentence_text": item.claim.sentence_text,
            "citation_text": bundle.context.in_text(item.references[0].id)
            if len(item.references) == 1
            else None,
            "reference_ids": [str(ref.id) for ref in item.references],
        }
        for item in bundle.accepted
    ]

    payload = {
        "draft": {"id": str(bundle.draft.id), "filename": bundle.draft.original_filename},
        "generated_at": datetime.now(UTC).isoformat(),
        "citation_style": citation_style,
        "insertion_mode": insertion_mode,
        "accepted": accepted,
        "audit": [audit_row_as_dict(row) for row in rows],
        "bibliography": bibliography,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
