"""One SDG (of 17) classified per paper, grounded in a real keyword phrase
from app/data/sdg_goals.json.

Two stages: a cheap regex prefilter (`sdg_keyword_matcher.prefilter`) scans
the whole draft text for free and narrows 1,636 keyword phrases down to a
shortlist of ~5 candidate goals; one LLM call then picks exactly one goal
and one keyword from that shortlist. The LLM never sees the full keyword
list -- only the shortlist, which keeps the prompt a few hundred tokens
instead of the 15-20k it would take to paste every goal's full list.
"""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Draft
from app.services.llm_client import Tier, get_llm_client
from app.services.sdg_keyword_matcher import GoalMatch, load_sdg_goals, prefilter

log = get_logger(__name__)

#: The prefilter scans the whole document for free (regex, not a model
#: call); this cap only controls prompt size for the one LLM call.
MAX_CLASSIFY_CHARS = 4000

SDG_SYSTEM = (
    "You classify an academic paper against the UN Sustainable Development "
    "Goals (SDGs). You are given a shortlist of candidate goals, each with "
    "keyword phrases from an established SDG keyword-search methodology "
    "that were found in the paper's text. Pick the single goal the paper "
    "is most centrally about, and the one keyword from that goal's list "
    "that best represents the match. Only use a goal number and keyword "
    "from the shortlist below -- never invent one. Return JSON only."
)

SDG_USER_TEMPLATE = """Paper text (excerpt):
{text}

Candidate SDGs (goal_number: name -- matched keywords):
{candidates}

Pick exactly one goal_number from the list above, and one keyword from
that goal's matched keywords."""


class SDGPick(BaseModel):
    goal_number: int
    keyword: str | None = None


def _format_candidates(candidates: list[GoalMatch]) -> str:
    lines = []
    for c in candidates:
        keywords = ", ".join(c.matched_keywords) or "(no keyword match -- goal name only)"
        lines.append(f"{c.number}: {c.name} -- {keywords}")
    return "\n".join(lines)


def _fallback_candidates() -> list[GoalMatch]:
    """No keyword hit anywhere: fall back to all 17 goal names, no keywords."""
    return [
        GoalMatch(number=g.number, name=g.name, matched_keywords=()) for g in load_sdg_goals()
    ]


def classify_draft(session: Session, draft: Draft) -> dict:
    """Classify one SDG for the draft; writes sdg_number/sdg_name/sdg_keyword.

    A no-op if raw_text is empty -- callers run this after parsing, so an
    empty draft here means parsing itself failed upstream.
    """
    text = draft.raw_text or ""
    if not text.strip():
        return {"classified": False, "reason": "no_text"}

    candidates = prefilter(text, top_n=5)
    used_fallback = not candidates
    if used_fallback:
        candidates = _fallback_candidates()

    client = get_llm_client()
    user = SDG_USER_TEMPLATE.format(
        text=text[:MAX_CLASSIFY_CHARS], candidates=_format_candidates(candidates)
    )
    pick = client.complete_structured(
        tier=Tier.CLASSIFY, system=SDG_SYSTEM, user=user, schema=SDGPick
    )

    by_number = {c.number: c for c in candidates}
    match = by_number.get(pick.goal_number)
    if match is None:
        # LLM picked outside the shortlist -- fall back to the top-ranked
        # candidate rather than trusting an ungrounded goal number.
        match = candidates[0]

    keyword = (
        pick.keyword
        if pick.keyword in match.matched_keywords
        else (match.matched_keywords[0] if match.matched_keywords else None)
    )

    draft.sdg_number = match.number
    draft.sdg_name = match.name
    draft.sdg_keyword = keyword
    session.commit()

    log.info(
        "sdg_classified",
        draft_id=str(draft.id),
        sdg=match.number,
        keyword=keyword,
        fallback=used_fallback,
    )
    return {
        "classified": True,
        "sdg_number": match.number,
        "sdg_name": match.name,
        "sdg_keyword": keyword,
    }
