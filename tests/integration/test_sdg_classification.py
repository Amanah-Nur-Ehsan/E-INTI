"""classify_draft against the real test DB, using the mock LLM client
(USE_MOCK_PROVIDERS=true globally in conftest.py routes Tier.CLASSIFY
calls to MockLLMClient._classify_sdg, which deterministically picks the
top-ranked prefilter candidate)."""

import pytest

from app.db.models import Draft
from app.services.sdg_classification_service import classify_draft

pytestmark = pytest.mark.integration


def _make_draft(db_session, raw_text: str | None) -> Draft:
    draft = Draft(
        original_filename="paper.docx",
        storage_path="/tmp/paper.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        raw_text=raw_text,
    )
    db_session.add(draft)
    db_session.commit()
    db_session.refresh(draft)
    return draft


def test_classifies_a_health_paper_as_sdg_3(db_session):
    draft = _make_draft(
        db_session,
        "This paper studies childhood vaccination programs and their effect on "
        "reducing infectious disease and infant mortality in rural clinics.",
    )

    result = classify_draft(db_session, draft)

    assert result["classified"] is True
    assert result["sdg_number"] == 3
    assert result["sdg_name"] == "Good health and well-being"
    assert result["sdg_keyword"] is not None

    db_session.refresh(draft)
    assert draft.sdg_number == 3
    assert draft.sdg_name == "Good health and well-being"
    assert draft.sdg_keyword == result["sdg_keyword"]


def test_empty_draft_text_is_not_classified(db_session):
    draft = _make_draft(db_session, raw_text=None)

    result = classify_draft(db_session, draft)

    assert result == {"classified": False, "reason": "no_text"}
    db_session.refresh(draft)
    assert draft.sdg_number is None


def test_text_with_no_keyword_hits_falls_back_to_all_goal_names(db_session):
    # Deliberately generic prose unlikely to hit any of the 1,636 keyword
    # phrases -- exercises the _fallback_candidates() path.
    draft = _make_draft(db_session, "Lorem ipsum dolor sit amet consectetur adipiscing elit.")

    result = classify_draft(db_session, draft)

    assert result["classified"] is True
    assert 1 <= result["sdg_number"] <= 17
