"""Builds a fill-in-the-abstract xlsx for one publication year (or unknown).

The header row exactly matches what dataset_import_service already
recognizes, so the round trip is: download, paste abstracts into the
ABSTRACT column, re-upload through the normal /library/import flow. That
upload hits the same DOI/title match as any other re-import and backfills
just the abstract on matching rows -- no separate upload mechanism, no
new column for the user to learn.
"""

from io import BytesIO

from openpyxl import Workbook

from app.db.models import ReferencePaper

HEADERS = [
    "NO.",
    "YEAR",
    "FIELD OF STUDY",
    "AUTHORS",
    "DOCUMENT TITLE",
    "SOURCE TITLE",
    "LINK",
    "ABSTRACT",
]


def _authors_to_text(authors: list[dict] | None) -> str:
    if not authors:
        return ""
    return "; ".join(a["name"] for a in authors if a.get("name"))


def build_missing_abstract_template(references: list[ReferencePaper]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Missing Abstracts"
    ws.append(HEADERS)
    for ref in references:
        ws.append(
            [
                ref.original_row_number,
                ref.year,
                ref.field_of_study,
                _authors_to_text(ref.authors),
                ref.title,
                ref.source_title,
                ref.source_link,
                "",
            ]
        )

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
