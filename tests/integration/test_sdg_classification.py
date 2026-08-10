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
    # A bare "SDG 3" the user can't interrogate is the thing the rationale
    # exists to prevent, so it must actually be persisted, not just returned.
    assert result["sdg_rationale"]

    db_session.refresh(draft)
    assert draft.sdg_number == 3
    assert draft.sdg_name == "Good health and well-being"
    assert draft.sdg_keyword == result["sdg_keyword"]
    assert draft.sdg_rationale == result["sdg_rationale"]


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


class _FakeSDGClient:
    """Returns a fixed SDGPick regardless of the prompt -- used to exercise
    classify_draft's fits/no-match handling independent of any real
    judgement call about what the mock or a real model would decide.
    """

    def __init__(self, payload: dict):
        self.payload = payload

    def complete_structured(self, *, tier, system, user, schema):
        return schema.model_validate(self.payload)


def test_fits_false_stores_no_sdg_but_keeps_rationale(db_session, monkeypatch):
    from app.services import sdg_classification_service as svc

    draft = _make_draft(
        db_session,
        "This paper proposes a novel fraud-detection framework for financial transactions.",
    )
    fake = _FakeSDGClient(
        {
            "fits": False,
            "goal_number": 13,
            "keyword": None,
            "reason": "Nothing here substantively concerns any of the 17 SDGs.",
        }
    )
    monkeypatch.setattr(svc, "get_llm_client", lambda: fake)

    result = svc.classify_draft(db_session, draft)

    assert result == {
        "classified": False,
        "reason": "no_match",
        "sdg_rationale": "Nothing here substantively concerns any of the 17 SDGs.",
    }
    db_session.refresh(draft)
    assert draft.sdg_number is None
    assert draft.sdg_name is None
    assert draft.sdg_keyword is None
    assert draft.sdg_rationale == "Nothing here substantively concerns any of the 17 SDGs."


def test_generic_keyword_with_fits_true_is_treated_as_no_match(db_session, monkeypatch):
    """Real-run regression: the model reported fits=True but the only
    matched keyword was the generic word 'framework', with nothing else
    backing up the SDG 13 pick -- the exact shape of the failure observed
    on a live fraud-detection paper classified as SDG 13 (Climate action).
    The backstop guard must decline even though the model didn't.
    """
    from app.services import sdg_classification_service as svc

    draft = _make_draft(
        db_session,
        "This paper proposes an adaptive retraining framework for financial fraud detection.",
    )
    fake = _FakeSDGClient(
        {
            "fits": True,
            "goal_number": 13,
            "keyword": "framework",
            "reason": "The paper mentions a framework, which matched SDG 13's keyword list.",
        }
    )
    monkeypatch.setattr(svc, "get_llm_client", lambda: fake)
    monkeypatch.setattr(
        svc,
        "prefilter",
        lambda text, top_n=5: [svc.GoalMatch(number=13, name="Climate action", matched_keywords=("framework",))],
    )

    result = svc.classify_draft(db_session, draft)

    assert result["classified"] is False
    assert result["reason"] == "no_match"
    db_session.refresh(draft)
    assert draft.sdg_number is None


def test_genuine_fit_with_generic_keyword_but_other_support_is_kept(db_session, monkeypatch):
    """The generic-keyword guard must not punish a goal that has a generic
    keyword AND a real, specific one -- only the case where generic is *all*
    there is.
    """
    from app.services import sdg_classification_service as svc

    draft = _make_draft(db_session, "A paper about a vaccination framework for infectious disease.")
    fake = _FakeSDGClient(
        {
            "fits": True,
            "goal_number": 3,
            "keyword": "framework",
            "reason": "The vaccination framework directly targets infectious disease control.",
        }
    )
    monkeypatch.setattr(svc, "get_llm_client", lambda: fake)
    monkeypatch.setattr(
        svc,
        "prefilter",
        lambda text, top_n=5: [
            svc.GoalMatch(
                number=3,
                name="Good health and well-being",
                matched_keywords=("framework", "infectious disease"),
            )
        ],
    )

    result = svc.classify_draft(db_session, draft)

    assert result["classified"] is True
    assert result["sdg_number"] == 3
