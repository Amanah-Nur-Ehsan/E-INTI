"""Import an .xlsx/.csv reference dataset into reference_papers.

Column names vary between researchers' spreadsheets, so headers are
normalized and matched against an alias table rather than required
verbatim. Import runs synchronously in the request — even a few thousand
rows parse in well under a second; only enrichment is asynchronous.
"""

import io
import re
from dataclasses import dataclass, field

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ReferencePaper
from app.db.models.enums import EnrichmentProvider, EnrichmentStatus
from app.services.identifier_extraction_service import extract_identifiers

#: canonical field -> accepted header spellings (normalized form)
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "title": ("DOCUMENT TITLE", "TITLE", "ARTICLE TITLE", "PAPER TITLE"),
    "source_link": ("LINK", "URL", "DOI LINK", "SCOPUS LINK", "SOURCE LINK"),
    "original_row_number": ("NO", "#", "INDEX", "ROW"),
    "year": ("YEAR", "PUBLICATION YEAR", "PUB YEAR", "COVER DATE"),
    "field_of_study": ("FIELD OF STUDY", "FIELD", "SUBJECT AREA", "DISCIPLINE"),
    "authors_raw": ("AUTHORS", "AUTHOR", "AUTHOR(S)", "AUTHOR NAMES"),
    "source_title": ("SOURCE TITLE", "JOURNAL", "SOURCE", "VENUE", "PUBLICATION NAME"),
    "doi": ("DOI",),
    "scopus_eid": ("EID", "SCOPUS EID"),
    "scopus_id": ("SCOPUS ID", "SCOPUS_ID", "SCP"),
    "abstract": ("ABSTRACT",),
    "author_keywords": ("AUTHOR KEYWORDS", "AUTHOR_KEYWORDS", "KEYWORDS"),
    "index_keywords": ("INDEX KEYWORDS", "INDEX_KEYWORDS"),
    "citation_count": ("CITATION COUNT", "CITED BY", "CITATIONS"),
    "document_type": ("DOCUMENT TYPE", "TYPE"),
}

REQUIRED_FIELDS = ("title", "source_link")

#: A dataset-supplied abstract this long is trusted; shorter values are
#: usually truncated teasers, so we still enrich those from Scopus.
MIN_TRUSTED_ABSTRACT_CHARS = 200


class DatasetSchemaError(ValueError):
    pass


@dataclass
class ImportSummary:
    imported: int = 0
    skipped_duplicates: int = 0
    skipped_invalid: int = 0
    warnings: list[str] = field(default_factory=list)


def normalize_header(header: str) -> str:
    text = re.sub(r"\s+", " ", str(header)).strip().upper()
    return text.rstrip(".:").strip()


def map_columns(headers: list[str]) -> dict[str, str]:
    """Return {canonical_field: original_header}."""
    normalized = {normalize_header(h): h for h in headers}
    mapping: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[canonical] = normalized[alias]
                break

    missing = [f for f in REQUIRED_FIELDS if f not in mapping]
    if missing:
        raise DatasetSchemaError(
            f"Dataset is missing required column(s): {', '.join(missing)}. "
            f"Found headers: {', '.join(str(h) for h in headers)}"
        )
    return mapping


#: How far down a sheet to look for the header row. Real exports often carry a
#: title banner and blank spacer rows above the actual column names.
MAX_HEADER_SCAN_ROWS = 12


def _score_header_row(values: list) -> int:
    """How many canonical fields this row's cells look like headers for."""
    normalized = {normalize_header(v) for v in values if v is not None and str(v) != "nan"}
    return sum(
        1
        for aliases in COLUMN_ALIASES.values()
        if any(alias in normalized for alias in aliases)
    )


def find_header_row(raw: pd.DataFrame) -> int:
    """Locate the header row, tolerating banner and spacer rows above it."""
    best_row, best_score = 0, -1
    for row in range(min(MAX_HEADER_SCAN_ROWS, len(raw))):
        score = _score_header_row(raw.iloc[row].tolist())
        if score > best_score:
            best_row, best_score = row, score
    return best_row


def _read_sheet(content: bytes, sheet_name) -> pd.DataFrame:
    raw = pd.read_excel(
        io.BytesIO(content), sheet_name=sheet_name, engine="openpyxl", dtype=str, header=None
    )
    if raw.empty:
        return pd.DataFrame()

    header_row = find_header_row(raw)
    frame = raw.iloc[header_row + 1 :].copy()
    frame.columns = [str(c) for c in raw.iloc[header_row].tolist()]
    frame["__sheet__"] = str(sheet_name)
    return frame


def read_table(content: bytes, filename: str) -> pd.DataFrame:
    """Read a dataset into one frame.

    Every sheet of a workbook is read and concatenated: reference lists are
    routinely split by publication year across tabs, and the candidate pool is
    meant to be the whole file.
    """
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        sheet_names = pd.ExcelFile(io.BytesIO(content), engine="openpyxl").sheet_names
        frames = []
        errors = []
        for sheet_name in sheet_names:
            frame = _read_sheet(content, sheet_name)
            if frame.empty:
                continue
            try:
                map_columns(list(frame.columns))
            except DatasetSchemaError as exc:
                errors.append(f"sheet '{sheet_name}': {exc}")
                continue
            frames.append(frame)
        if not frames:
            raise DatasetSchemaError(
                "No sheet contained the required columns. " + " | ".join(errors)
            )
        return pd.concat(frames, ignore_index=True)

    if name.endswith((".csv", ".tsv", ".txt")):
        sep = "\t" if name.endswith(".tsv") else ","
        for encoding in ("utf-8-sig", "latin-1"):
            try:
                raw = pd.read_csv(
                    io.BytesIO(content), sep=sep, dtype=str, encoding=encoding, header=None
                )
            except UnicodeDecodeError:
                continue
            header_row = find_header_row(raw)
            frame = raw.iloc[header_row + 1 :].copy()
            frame.columns = [str(c) for c in raw.iloc[header_row].tolist()]
            return frame
        raise DatasetSchemaError("Could not decode CSV as UTF-8 or Latin-1")

    raise DatasetSchemaError(f"Unsupported dataset format: {filename}")


def _clean(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() in ("nan", "none", "n/a", "-"):
        return None
    return text


def _to_int(value) -> int | None:
    text = _clean(value)
    if text is None:
        return None
    match = re.search(r"\d{1,4}", text)
    return int(match.group(0)) if match else None


def split_keywords(value) -> list[str] | None:
    text = _clean(value)
    if text is None:
        return None
    parts = [p.strip() for p in re.split(r"[;|]", text) if p.strip()]
    return parts or None


def split_authors(value) -> list[dict] | None:
    text = _clean(value)
    if text is None:
        return None
    parts = [p.strip() for p in re.split(r"[;]|(?:,\s(?=[A-Z][a-z]))", text) if p and p.strip()]
    return [{"name": p} for p in parts] or None


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def import_dataset(session: Session, content: bytes, filename: str) -> ImportSummary:
    """Import into the shared library. Duplicates (by DOI, then EID, then
    normalized title for rows with neither) are skipped against the whole
    library, not just this file -- re-uploading the same dataset, or one
    with overlapping rows, adds only what's actually new.
    """
    frame = read_table(content, filename)
    mapping = map_columns(list(frame.columns))
    summary = ImportSummary()

    existing = session.execute(
        select(ReferencePaper.doi, ReferencePaper.scopus_eid, ReferencePaper.title)
    ).all()
    seen_dois = {d for d, _, _ in existing if d}
    seen_eids = {e for _, e, _ in existing if e}
    seen_titles = {normalize_title(t) for _, _, t in existing if t}

    def col(row, canonical: str):
        header = mapping.get(canonical)
        return row[header] if header else None

    for position, (_, row) in enumerate(frame.iterrows(), start=1):
        title = _clean(col(row, "title"))
        if not title:
            summary.skipped_invalid += 1
            continue

        ids = extract_identifiers(
            link=_clean(col(row, "source_link")),
            doi_column=_clean(col(row, "doi")),
            eid_column=_clean(col(row, "scopus_eid")),
        )

        norm_title = normalize_title(title)
        if (
            (ids.doi and ids.doi in seen_dois)
            or (ids.scopus_eid and ids.scopus_eid in seen_eids)
            or (not ids.has_any and norm_title in seen_titles)
        ):
            summary.skipped_duplicates += 1
            continue

        abstract = _clean(col(row, "abstract"))
        trusted_abstract = abstract if abstract and len(abstract) >= MIN_TRUSTED_ABSTRACT_CHARS else None

        reference = ReferencePaper(
            original_row_number=_to_int(col(row, "original_row_number")) or position,
            original_data={str(k): _clean(v) for k, v in row.items()},
            title=title,
            abstract=trusted_abstract,
            authors=split_authors(col(row, "authors_raw")),
            year=_to_int(col(row, "year")),
            source_title=_clean(col(row, "source_title")),
            field_of_study=_clean(col(row, "field_of_study")),
            doi=ids.doi,
            scopus_eid=ids.scopus_eid,
            scopus_id=ids.scopus_id or _clean(col(row, "scopus_id")),
            semantic_scholar_id=ids.semantic_scholar_id,
            author_keywords=split_keywords(col(row, "author_keywords")),
            index_keywords=split_keywords(col(row, "index_keywords")),
            source_link=_clean(col(row, "source_link")),
            citation_count=_to_int(col(row, "citation_count")),
            document_type=_clean(col(row, "document_type")),
            enrichment_status=(
                EnrichmentStatus.ENRICHED if trusted_abstract else EnrichmentStatus.PENDING
            ),
            enrichment_provider=EnrichmentProvider.DATASET if trusted_abstract else None,
        )
        session.add(reference)

        if ids.doi:
            seen_dois.add(ids.doi)
        if ids.scopus_eid:
            seen_eids.add(ids.scopus_eid)
        seen_titles.add(norm_title)
        summary.imported += 1

        if not ids.has_any:
            summary.warnings.append(
                f"Row {position}: no DOI/EID found in LINK; enrichment will likely be incomplete"
            )

    session.commit()
    # Keep the response readable when a whole sheet lacks identifiers.
    if len(summary.warnings) > 10:
        remaining = len(summary.warnings) - 10
        summary.warnings = summary.warnings[:10] + [f"...and {remaining} more rows without identifiers"]
    return summary
