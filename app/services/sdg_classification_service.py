"""One SDG (of 17) classified per paper, grounded in a real keyword phrase
from app/data/sdg_goals.json.

Two stages: a cheap regex prefilter (`sdg_keyword_matcher.prefilter`) scans
the whole draft text for free and narrows 1,636 keyword phrases down to a
shortlist of ~5 candidate goals; one LLM call then picks exactly one goal
and one keyword from that shortlist. The LLM never sees the full keyword
list -- only the shortlist, which keeps the prompt a few hundred tokens
instead of the 15-20k it would take to paste every goal's full list. The
remaining goals are still sent, as bare names with no keywords, so the
model can choose a genuinely-fitting SDG the keyword prefilter simply
didn't lexically match -- that costs almost nothing (`_fallback_candidates`
already proves the pattern) and matters once the model is also allowed to
say "none of these fit" (see `fits` below).

A paper can genuinely match none of the 17 goals. The shortlist is built
from *keyword* matches, which are lexical, not semantic -- "framework"
appears in SDG 13's keyword list, so a paper about an unrelated framework
can shortlist Climate action despite having nothing to do with it. Without
an explicit way to decline, the schema forces a pick regardless, and the
model's only channel to object is prose in the `reason` field that nothing
downstream reads -- observed on a real run where a fraud-detection paper
was classified SDG 13 with a rationale that literally said the match
didn't hold. `SDGPick.fits` exists so "no confident match" is a real,
representable, actionable answer instead of a forced guess.
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
    "Goals (SDGs) using only the official goal names and keyword phrases "
    "contained in the file titled 'SDG Goals Keywords as of 2026'. "
    "You are given a candidate list generated from that file: some candidates "
    "include keyword phrases from their SDG group that were lexically matched "
    "in the paper text, others are bare goal names with no keyword match. "
    "A keyword match is a lexical signal, not proof of relevance -- a generic "
    "word like 'framework' can match a goal's keyword list even when the "
    "paper has nothing to do with that goal. "
    "First decide whether the paper is genuinely, substantively about ANY "
    "candidate's theme -- its central research objective, application domain, "
    "problem, or measured outcome, not merely a shared word. If yes, set fits "
    "to true and select that single SDG, plus (if it had one) the single "
    "matched keyword from that same SDG group that best represents the "
    "paper's actual topic, contribution, object, or measured outcome. If no "
    "candidate genuinely fits, set fits to false -- do not force a selection. "
    "Do not select a goal, or set fits to true, merely because a generic word "
    "such as 'framework', 'model', 'system', 'innovation', 'technology', or "
    "'management' appears in the paper. The keyword must be interpreted "
    "within the thematic context of its SDG group in 'SDG Goals Keywords as "
    "of 2026'. "
    "Prioritize direct alignment with the paper's research objective, domain, "
    "problem, evidence, and demonstrated outcome. Reject candidates supported "
    "only by lexical similarity, speculative future applications, or indirect "
    "associations -- for those, set fits to false. "
    "Use only a goal_number, goal_name, and keyword provided in the candidate "
    "list. Never invent, rewrite, normalize, translate, singularize, "
    "pluralize, or move a keyword between SDG groups. Preserve the keyword "
    "exactly as supplied, including punctuation, capitalization, hyphens, and "
    "asterisks. "
    "Return valid JSON only, with exactly these keys: fits, goal_number, "
    "goal_name, keyword, reason. When fits is false, still supply your best "
    "guess for goal_number/goal_name (unused for storage) so the JSON stays "
    "well-formed, but keyword must be null. The reason must be one sentence: "
    "when fits is true, identify the specific research objective, "
    "application, evidence, or measured outcome that directly connects the "
    "paper to the selected SDG; when fits is false, explain briefly why none "
    "of the candidates substantively apply."
)

SDG_USER_TEMPLATE = """Paper text (excerpt):
{text}

Candidate SDGs extracted from the file "SDG Goals Keywords as of 2026":

{candidates}

Each candidate follows this structure:

goal_number: SDG name
matched_keywords:
- exact keyword from that SDG group
- exact keyword from that SDG group

("(no keyword match -- goal name only)" means this goal was not lexically
matched; it's included so you can still choose it on genuine thematic fit.)

Decide, then select exactly:
1. fits: true only if the paper is genuinely, substantively about one of
   these candidates' themes; false if none of them really apply;
2. one goal_number from the candidate list (your best guess if fits=false);
3. the corresponding goal_name exactly as supplied;
4. one keyword from that goal's matched_keywords, reproduced exactly -- null
   if fits=false, or if the chosen goal had no keyword match; and
5. one sentence explaining the paper-level evidence for the selection (or,
   if fits=false, why nothing fit).

Selection rules:
- Choose the SDG that best matches the paper's central research purpose,
  application domain, problem, contribution, and measured outcome.
- Treat the candidate keywords as terms sourced from "SDG Goals Keywords as
  of 2026", not as independent generic labels.
- Interpret every keyword within the context of its own SDG group.
- Do not choose based only on a shared word, and do not set fits=true based
  only on a shared word.
- A generic keyword such as "framework" is valid only when the proposed
  framework directly concerns the substantive theme of that SDG.
- Do not use possible future applications as evidence unless they are directly
  investigated in the paper.
- Do not invent or modify the goal number, goal name, or keyword.
- When genuinely uncertain, prefer fits=false over a forced guess.
- Return JSON only."""


#: A goal picked on nothing but one of these, with no other supporting
#: keyword, is exactly the failure `fits` exists to catch -- kept here as a
#: backstop in case the model sets fits=true without noticing. Mirrors the
#: same list the prompt above already warns against.
_GENERIC_KEYWORDS = {"framework", "model", "system", "innovation", "technology", "management"}


class SDGPick(BaseModel):
    fits: bool = True
    goal_number: int
    keyword: str | None = None
    reason: str = ""


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


def _augment_with_unmatched(candidates: list[GoalMatch]) -> list[GoalMatch]:
    """Append every goal the keyword prefilter didn't shortlist, as bare
    names with no keywords -- so the model can still choose a genuinely
    fitting SDG the lexical prefilter missed, the same way
    `_fallback_candidates` already does when nothing matched at all. Cheap:
    goal names alone, no keyword lists, a few hundred tokens for the
    remaining ~12 goals.
    """
    have = {c.number for c in candidates}
    unmatched = [
        GoalMatch(number=g.number, name=g.name, matched_keywords=())
        for g in load_sdg_goals()
        if g.number not in have
    ]
    return list(candidates) + unmatched


def classify_draft(session: Session, draft: Draft) -> dict:
    """Classify one SDG for the draft; writes sdg_number/sdg_name/sdg_keyword.

    A no-op if raw_text is empty -- callers run this after parsing, so an
    empty draft here means parsing itself failed upstream.

    Not every paper matches one of the 17 goals. When the model reports
    `fits=False` -- or reports `fits=True` on nothing but a generic keyword
    with no other support, which the guard below treats the same way -- no
    SDG is stored. `sdg_rationale` is kept even then: it explains why
    nothing matched, which is the whole point of asking for a reason.
    """
    text = draft.raw_text or ""
    if not text.strip():
        return {"classified": False, "reason": "no_text"}

    candidates = prefilter(text, top_n=5)
    used_fallback = not candidates
    if used_fallback:
        candidates = _fallback_candidates()
    else:
        candidates = _augment_with_unmatched(candidates)

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
        # LLM picked outside the candidate list -- fall back to the
        # top-ranked candidate rather than trusting an ungrounded goal
        # number. Only reachable when fits=True, since a false pick's
        # goal_number is never stored.
        match = candidates[0]

    keyword = (
        pick.keyword
        if pick.keyword in match.matched_keywords
        else (match.matched_keywords[0] if match.matched_keywords else None)
    )

    fits = pick.fits
    if fits and keyword and keyword.strip().lower() in _GENERIC_KEYWORDS:
        # The model said it fits, but the only support is one of the
        # generic words the prompt explicitly warns against, and the goal
        # had no other matched keyword to back it up -- this is precisely
        # the lexical-accident failure `fits` exists to catch. Treat it as
        # a decline even though the model didn't flag it as one.
        non_generic = [k for k in match.matched_keywords if k.strip().lower() not in _GENERIC_KEYWORDS]
        if not non_generic:
            fits = False

    reason = (pick.reason or "").strip() or None

    if not fits:
        draft.sdg_number = None
        draft.sdg_name = None
        draft.sdg_keyword = None
        draft.sdg_rationale = reason
        session.commit()

        log.info(
            "sdg_no_match",
            draft_id=str(draft.id),
            considered=match.number,
            fallback=used_fallback,
        )
        return {
            "classified": False,
            "reason": "no_match",
            "sdg_rationale": reason,
        }

    draft.sdg_number = match.number
    draft.sdg_name = match.name
    draft.sdg_keyword = keyword
    draft.sdg_rationale = reason
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
        "sdg_rationale": draft.sdg_rationale,
    }
