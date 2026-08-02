"""Matches draft text against the UN SDG keyword-search strategy.

`app/data/sdg_goals.json` is the Elsevier/Scopus SDG-mapping keyword list:
17 goals, each with a set of Scopus-style boolean search terms. Two things
about that format matter for matching:

- `*` is a wildcard for zero or more characters (e.g. "vaccin*" matches
  "vaccine", "vaccination"); `?` is a wildcard for exactly one character
  (e.g. "democrati?ation" matches the -s- and -z- spellings).
- A term containing " and " is a boolean AND, not a literal phrase: every
  sub-term must appear somewhere in the text, not necessarily adjacent
  (e.g. "marine and coral bleaching" matches text that mentions "marine"
  anywhere and "coral bleaching" anywhere). This is how the source
  methodology's search strings are meant to be run against a corpus.

This module only prefilters -- it narrows ~1,600 keywords down to a
shortlist of candidate goals cheaply (no LLM call), which
`sdg_classification_service` then hands to the LLM to make the final,
grounded pick from.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "sdg_goals.json"


@dataclass(frozen=True)
class SDGGoal:
    number: int
    name: str
    keywords: tuple[str, ...]


@lru_cache
def load_sdg_goals() -> tuple[SDGGoal, ...]:
    raw = json.loads(DATA_PATH.read_text())
    return tuple(
        SDGGoal(number=g["number"], name=g["name"], keywords=tuple(g["keywords"])) for g in raw
    )


def _term_to_pattern(term: str) -> re.Pattern:
    escaped = re.escape(term.strip())
    escaped = escaped.replace(r"\*", ".*").replace(r"\?", ".")
    return re.compile(escaped, re.IGNORECASE)


@lru_cache
def _compiled_keywords() -> tuple[tuple[int, str, tuple[re.Pattern, ...]], ...]:
    """(goal_number, original_keyword_phrase, sub_term_patterns) for every keyword.

    A boolean "X and Y" phrase compiles to multiple patterns, all of which
    must match; a plain phrase compiles to a single pattern.
    """
    compiled = []
    for goal in load_sdg_goals():
        for kw in goal.keywords:
            sub_terms = re.split(r"\s+and\s+", kw) if " and " in kw.lower() else [kw]
            patterns = tuple(_term_to_pattern(t) for t in sub_terms)
            compiled.append((goal.number, kw, patterns))
    return tuple(compiled)


@dataclass(frozen=True)
class GoalMatch:
    number: int
    name: str
    #: Matched keyword phrases, longest (most specific) first.
    matched_keywords: tuple[str, ...]


def prefilter(text: str, top_n: int = 5, max_keywords_per_goal: int = 10) -> list[GoalMatch]:
    """Rank SDG goals by how many of their keyword phrases match `text`.

    Returns the top_n goals by match count, each carrying the keyword
    phrases that actually matched -- this shortlist is what the LLM picks
    from, so the final classification is always grounded in a real entry
    from the source list rather than a freeform guess.
    """
    if not text or not text.strip():
        return []

    hits: dict[int, list[str]] = {}
    for goal_number, phrase, patterns in _compiled_keywords():
        if all(p.search(text) for p in patterns):
            hits.setdefault(goal_number, []).append(phrase)

    names = {g.number: g.name for g in load_sdg_goals()}
    ranked = sorted(hits.items(), key=lambda item: len(item[1]), reverse=True)

    results = []
    for number, phrases in ranked[:top_n]:
        phrases_sorted = sorted(phrases, key=len, reverse=True)
        results.append(
            GoalMatch(
                number=number,
                name=names[number],
                matched_keywords=tuple(phrases_sorted[:max_keywords_per_goal]),
            )
        )
    return results
