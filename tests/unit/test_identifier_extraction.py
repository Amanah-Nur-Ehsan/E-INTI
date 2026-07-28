import pytest

from app.services.identifier_extraction_service import (
    LinkKind,
    extract_identifiers,
    normalize_doi,
)


@pytest.mark.parametrize(
    "link,expected_doi,expected_eid,expected_kind",
    [
        (
            "https://www.scopus.com/inward/record.uri?eid=2-s2.0-85123456789&partnerID=40",
            None,
            "2-s2.0-85123456789",
            LinkKind.SCOPUS,
        ),
        ("https://doi.org/10.1016/j.eswa.2024.123456", "10.1016/j.eswa.2024.123456", None, LinkKind.DOI),
        (
            "http://dx.doi.org/10.1109/ACCESS.2023.3298765",
            "10.1109/access.2023.3298765",
            None,
            LinkKind.DOI,
        ),
        ("10.1145/3580305.3599876", "10.1145/3580305.3599876", None, LinkKind.DOI),
        (
            "https://link.springer.com/article/10.1007/s10462-023-10429-z",
            "10.1007/s10462-023-10429-z",
            None,
            LinkKind.PUBLISHER,
        ),
        (
            "https://www.semanticscholar.org/paper/Title-Slug/0123456789abcdef0123456789abcdef01234567",
            None,
            None,
            LinkKind.SEMANTIC_SCHOLAR,
        ),
        ("https://example.org/some/landing/page", None, None, LinkKind.PUBLISHER),
        ("", None, None, LinkKind.UNKNOWN),
        (None, None, None, LinkKind.UNKNOWN),
    ],
)
def test_link_permutations(link, expected_doi, expected_eid, expected_kind):
    result = extract_identifiers(link)
    assert result.doi == expected_doi
    assert result.scopus_eid == expected_eid
    assert result.kind == expected_kind


def test_percent_encoded_doi_in_scopus_url():
    link = "https://www.scopus.com/record/display.uri?doi=10.1016%2Fj.ins.2022.01.045"
    result = extract_identifiers(link)
    assert result.doi == "10.1016/j.ins.2022.01.045"


def test_trailing_punctuation_is_stripped():
    assert normalize_doi("See (10.1016/j.eswa.2024.123456).") == "10.1016/j.eswa.2024.123456"
    assert normalize_doi("10.1109/TSE.2021.3054321;") == "10.1109/tse.2021.3054321"


def test_explicit_columns_win_over_link():
    result = extract_identifiers(
        link="https://doi.org/10.1000/from-link",
        doi_column="10.2000/from-column",
        eid_column="2-s2.0-99999999999",
    )
    assert result.doi == "10.2000/from-column"
    assert result.scopus_eid == "2-s2.0-99999999999"


def test_bare_eid_without_url():
    result = extract_identifiers("2-s2.0-85011122233")
    assert result.scopus_eid == "2-s2.0-85011122233"
    assert result.kind == LinkKind.SCOPUS


def test_scopus_scp_id_captured():
    result = extract_identifiers("https://www.scopus.com/inward/citedby.uri?scp=85123456789")
    assert result.scopus_id == "85123456789"


def test_has_any_flag():
    assert extract_identifiers("10.1016/j.eswa.2024.1").has_any
    assert not extract_identifiers("https://nowhere.example/page").has_any


def test_short_registrant_is_not_a_doi():
    # DOI registrant codes are 4-9 digits; "10.1/x" is not a DOI.
    assert normalize_doi("10.1/x") is None
