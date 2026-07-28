import pytest

from app.services.dataset_import_service import (
    DatasetSchemaError,
    map_columns,
    normalize_header,
    split_authors,
    split_keywords,
)


def test_normalize_header_strips_punctuation_and_case():
    assert normalize_header("  document   title. ") == "DOCUMENT TITLE"
    assert normalize_header("No.") == "NO"


def test_map_columns_accepts_spec_headers():
    mapping = map_columns(
        ["NO.", "YEAR", "FIELD OF STUDY", "AUTHORS", "DOCUMENT TITLE", "SOURCE TITLE", "LINK"]
    )
    assert mapping["title"] == "DOCUMENT TITLE"
    assert mapping["source_link"] == "LINK"
    assert mapping["original_row_number"] == "NO."


def test_map_columns_accepts_aliases():
    mapping = map_columns(["Title", "URL", "Journal"])
    assert mapping["title"] == "Title"
    assert mapping["source_link"] == "URL"
    assert mapping["source_title"] == "Journal"


def test_map_columns_reports_missing_required():
    with pytest.raises(DatasetSchemaError) as exc:
        map_columns(["YEAR", "AUTHORS"])
    message = str(exc.value)
    assert "title" in message and "source_link" in message
    assert "YEAR" in message  # found headers echoed back for debugging


def test_split_keywords_handles_semicolons_and_blanks():
    assert split_keywords("fraud detection; machine learning") == [
        "fraud detection",
        "machine learning",
    ]
    assert split_keywords("") is None
    assert split_keywords(None) is None


def test_split_authors_produces_name_dicts():
    assert split_authors("Smith, J.; Doe, A.") == [{"name": "Smith, J."}, {"name": "Doe, A."}]
