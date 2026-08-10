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
        "sdg_closest_number": 13,
        "sdg_closest_name": "Climate action",
    }
    db_session.refresh(draft)
    assert draft.sdg_number is None
    assert draft.sdg_name is None
    assert draft.sdg_keyword is None
    assert draft.sdg_rationale == "Nothing here substantively concerns any of the 17 SDGs."
    # The declined candidate is still recorded, unconfirmed, so the user
    # has something to look at instead of a dead end.
    assert draft.sdg_closest_number == 13
    assert draft.sdg_closest_name == "Climate action"


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


def test_a_correct_goal_ranked_below_the_naive_top_5_still_keeps_its_keyword(db_session, monkeypatch):
    """Regression test: a paper that lexically matches several goals more
    heavily than the one it's actually about used to lose that goal's
    keyword entirely. Capping the shortlist at the top 5 *by match count*
    (not "does it have a match at all") meant a goal ranked 6th was
    appended to the prompt as a bare name with zero keywords -- so even
    when the model correctly identified it, there was no keyword left to
    pick from, and sdg_keyword silently came back None. This text lexically
    favours 6 other goals (2 matched keywords each) over the paper's real
    topic, "Good health and well-being" (1 match, ranked 6th).
    """
    from app.services import sdg_classification_service as svc

    draft = _make_draft(
        db_session,
        "This study of extreme poverty and poverty alleviation examines rural "
        "households. It also considers land tenure rights and childhood "
        "malnutrition in the region. We study school access and education "
        "quality outcomes. Gender inequality and employment equity gaps are "
        "also assessed. Freshwater availability and water scarcity are "
        "surveyed across basins. Energy efficiency and energy transition "
        "policies are compared. The cohort's primary outcome was "
        "cardiovascular disease incidence.",
    )
    fake = _FakeSDGClient(
        {
            "fits": True,
            "goal_number": 3,
            "keyword": "cardiovascular disease",
            "reason": "The paper's primary outcome is cardiovascular disease incidence.",
        }
    )
    monkeypatch.setattr(svc, "get_llm_client", lambda: fake)

    result = svc.classify_draft(db_session, draft)

    assert result["classified"] is True
    assert result["sdg_number"] == 3
    assert result["sdg_name"] == "Good health and well-being"
    assert result["sdg_keyword"] == "cardiovascular disease"


def test_keyword_never_equals_the_goal_name(db_session, monkeypatch):
    """Observed live: the exported paper's Keywords line ended up with the
    SDG group's own cluster name ("Good health and well-being") appended
    as if it were a keyword, instead of a real phrase from inside that
    group's keyword list (app/data/sdg_goals.json). A keyword must come
    from *inside* the group, never be the group label itself -- guarded
    explicitly at the point of use, independent of whatever upstream
    combination of model output and candidate data produced it.
    """
    from app.services import sdg_classification_service as svc

    draft = _make_draft(db_session, "A paper about auscultation and heart sound analysis.")
    fake = _FakeSDGClient(
        {
            "fits": True,
            "goal_number": 3,
            "keyword": "Good health and well-being",
            "reason": "The paper concerns health monitoring.",
        }
    )
    monkeypatch.setattr(svc, "get_llm_client", lambda: fake)
    # Constructed so the existing keyword-selection fallback alone would
    # reproduce the bug: matched_keywords contains exactly the string the
    # model echoed, so `pick.keyword in match.matched_keywords` is True and
    # the ordinary path accepts it -- this is the case the explicit
    # name-equality guard in classify_draft exists to catch.
    monkeypatch.setattr(
        svc,
        "prefilter",
        lambda text, top_n=17: [
            svc.GoalMatch(
                number=3,
                name="Good health and well-being",
                matched_keywords=("Good health and well-being",),
            )
        ],
    )

    result = svc.classify_draft(db_session, draft)

    assert result["classified"] is True
    assert result["sdg_number"] == 3
    assert result["sdg_keyword"] != "Good health and well-being"
    # The name-equality guard clears the bad value, then the keyword-only
    # follow-up call fills in a real phrase from SDG 3's full list instead
    # of leaving the paper with no keyword at all.
    goal_3 = next(g for g in svc.load_sdg_goals() if g.number == 3)
    assert result["sdg_keyword"] in goal_3.keywords


def test_a_genuinely_matched_goal_with_no_lexical_keyword_still_gets_a_real_one(db_session, monkeypatch):
    """Observed live: a paper about "auscultation" and "clinical decision
    support" was correctly classified SDG 3, but none of SDG 3's 99
    keyword phrases (e.g. "cardiovascular disease", "human health*")
    happen to appear verbatim in that text, so the paper came back with
    no keyword at all -- an SDG confirmed but nothing to show or write
    into the Keywords line. Confirmed with the user: once a goal is
    genuinely confirmed, let the model choose a keyword from that goal's
    full list even without a literal text match, rather than leaving the
    field empty.
    """
    from app.services import sdg_classification_service as svc

    draft = _make_draft(
        db_session, "Explainable AI for auscultation and clinical decision support."
    )
    # The main classification call reports fits=True for SDG 3 but with no
    # matched_keywords -- exactly the bare-name-candidate shape, since the
    # prefilter found zero literal hits for this text.
    main_pick = {
        "fits": True,
        "goal_number": 3,
        "keyword": None,
        "reason": "The paper concerns clinical health monitoring.",
    }
    # The keyword-only follow-up call gets the full SDG 3 list and picks a
    # real phrase from it.
    followup_pick = {"keyword": "public health"}
    calls: list[dict] = [main_pick, followup_pick]

    class _SequencedFakeClient:
        def complete_structured(self, *, tier, system, user, schema):
            return schema.model_validate(calls.pop(0))

    monkeypatch.setattr(svc, "get_llm_client", lambda: _SequencedFakeClient())
    monkeypatch.setattr(
        svc,
        "prefilter",
        lambda text, top_n=17: [
            svc.GoalMatch(number=3, name="Good health and well-being", matched_keywords=())
        ],
    )

    result = svc.classify_draft(db_session, draft)

    assert result["classified"] is True
    assert result["sdg_number"] == 3
    assert result["sdg_name"] == "Good health and well-being"
    assert result["sdg_keyword"] == "public health"
