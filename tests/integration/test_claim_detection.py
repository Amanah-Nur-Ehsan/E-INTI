import pytest

from app.db.models.enums import ClaimType, DetectionMethod, ExistingCitationStatus
from app.services.claim_detection_service import detect_and_store_claims
from app.services.draft_parser_service import parse_and_store_draft
from tests.conftest import upload_draft

pytestmark = pytest.mark.integration


@pytest.fixture
async def parsed_draft(client, db_session):
    draft_id = await upload_draft(client)
    parse_and_store_draft(db_session, draft_id)
    return draft_id


async def test_detection_produces_expected_claim_set(client, db_session, parsed_draft):
    counts = detect_and_store_claims(db_session, parsed_draft)
    assert counts["claims"] > 0
    assert counts["needs_citation"] > 0
    assert counts["llm_calls"] >= 1

    claims = (await client.get(f"/api/v1/drafts/{parsed_draft}/claims")).json()
    by_text = {c["sentence_text"]: c for c in claims}

    opener = next(t for t in by_text if t.startswith("Machine learning techniques have improved"))
    assert by_text[opener]["needs_citation"] is True
    assert by_text[opener]["detection_method"] == DetectionMethod.LLM
    assert by_text[opener]["section_title"] == "Introduction"
    assert by_text[opener]["keywords"]

    # Author-contribution and structural sentences never become claims.
    assert not any("This study uses a quantitative" in t for t in by_text)
    assert not any(t.startswith("The next section describes") for t in by_text)
    assert not any(t.startswith("Table 2 presents") for t in by_text)


async def test_existing_citations_are_recorded_not_reclaimed(client, db_session, parsed_draft):
    detect_and_store_claims(db_session, parsed_draft)
    claims = (await client.get(f"/api/v1/drafts/{parsed_draft}/claims")).json()

    cited = [c for c in claims if c["existing_citation_status"] != "NO_CITATION_FOUND"]
    texts = {c["sentence_text"] for c in cited}
    assert any("blockchain increases transparency" in t.lower() for t in texts)
    assert any("Smith et al. (2024)" in t for t in texts)

    bracket = next(c for c in cited if "[2]" in c["sentence_text"])
    assert bracket["existing_citation_text"] == "[2]"
    assert bracket["existing_citation_status"] == ExistingCitationStatus.CITATION_EXISTS_NOT_CHECKED


async def test_claim_offsets_still_slice_out_of_raw_text(client, db_session, parsed_draft):
    detect_and_store_claims(db_session, parsed_draft)
    detail = (await client.get(f"/api/v1/drafts/{parsed_draft}")).json()
    claims = (await client.get(f"/api/v1/drafts/{parsed_draft}/claims")).json()

    raw = detail["raw_text"]
    for claim in claims:
        assert raw[claim["char_start"] : claim["char_end"]] == claim["sentence_text"]


async def test_claim_types_are_valid_enum_members(client, db_session, parsed_draft):
    detect_and_store_claims(db_session, parsed_draft)
    claims = (await client.get(f"/api/v1/drafts/{parsed_draft}/claims")).json()
    assert all(c["claim_type"] in ClaimType.__members__ for c in claims)


async def test_detection_is_idempotent(client, db_session, parsed_draft):
    first = detect_and_store_claims(db_session, parsed_draft)
    second = detect_and_store_claims(db_session, parsed_draft)
    assert first["claims"] == second["claims"]

    claims = (await client.get(f"/api/v1/drafts/{parsed_draft}/claims")).json()
    assert len(claims) == first["claims"]


async def test_second_run_makes_zero_tier1_calls(client, db_session, parsed_draft):
    """The Tier-1 classification cache: an unchanged re-run must not spend
    another LLM call per sentence, and must produce the identical decision
    set it cached the first time.
    """
    first = detect_and_store_claims(db_session, parsed_draft)
    assert first["llm_calls"] >= 1

    second = detect_and_store_claims(db_session, parsed_draft)
    assert second["llm_calls"] == 0
    assert second["needs_citation"] == first["needs_citation"]
    assert second["claims"] == first["claims"]


async def test_needs_citation_filter(client, db_session, parsed_draft):
    detect_and_store_claims(db_session, parsed_draft)
    filtered = (
        await client.get(f"/api/v1/drafts/{parsed_draft}/claims?needs_citation=true")
    ).json()
    assert filtered
    assert all(c["needs_citation"] for c in filtered)


async def test_parallel_batches_still_map_decisions_to_the_right_sentence(
    client, db_session, parsed_draft, monkeypatch, settings
):
    """Tier-1 batches now run in a thread pool. Forcing batch_size=1 turns
    every uncached sentence into its own concurrently-run batch -- the
    worst case for index misalignment, since every batch races every other
    one. Results must still land on the correct sentence, identical to the
    known-correct outcome test_detection_produces_expected_claim_set
    asserts for the default (serial-in-practice, one batch) case.
    """
    monkeypatch.setattr(settings, "classify_batch_size", 1)

    counts = detect_and_store_claims(db_session, parsed_draft)
    assert counts["llm_calls"] > 1, "test needs multiple concurrent batches to be meaningful"

    claims = (await client.get(f"/api/v1/drafts/{parsed_draft}/claims")).json()
    by_text = {c["sentence_text"]: c for c in claims}

    opener = next(t for t in by_text if t.startswith("Machine learning techniques have improved"))
    assert by_text[opener]["needs_citation"] is True
    assert by_text[opener]["section_title"] == "Introduction"

    assert not any("This study uses a quantitative" in t for t in by_text)
    assert not any(t.startswith("The next section describes") for t in by_text)
    assert not any(t.startswith("Table 2 presents") for t in by_text)
