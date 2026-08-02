"""The keyword prefilter that shortlists SDG candidates before the LLM
picks the final one -- wildcard handling and the boolean "and" semantics
are the two non-trivial pieces of logic here.
"""

from app.services.sdg_keyword_matcher import load_sdg_goals, prefilter


def test_loads_seventeen_goals_with_keywords():
    goals = load_sdg_goals()
    assert len(goals) == 17
    assert {g.number for g in goals} == set(range(1, 18))
    assert all(g.keywords for g in goals)


def test_star_wildcard_matches_variants():
    # "vaccin*" (SDG 3) must match "vaccination", not just the literal "vaccin".
    matches = prefilter("A study on childhood vaccination programs.")
    assert any(m.number == 3 for m in matches)
    goal_3 = next(m for m in matches if m.number == 3)
    assert any("vaccin" in kw for kw in goal_3.matched_keywords)


def test_question_mark_wildcard_matches_single_char_variants():
    # "fertili?er" (SDG 2) must match both the -s- and -z- spellings.
    for spelling in ("fertiliser", "fertilizer"):
        matches = prefilter(f"A study on {spelling} use in smallholder farming.")
        assert any(m.number == 2 for m in matches), spelling


def test_boolean_and_requires_both_terms_present_not_adjacent():
    # "marine and coral bleaching" (SDG 14) is a boolean AND: both terms
    # must appear somewhere in the text, not as an adjacent phrase.
    text = "This paper discusses coral bleaching. Elsewhere it covers marine ecosystems."
    matches = prefilter(text)
    assert any(m.number == 14 for m in matches)

    # A text with only one of the two terms must not match that keyword.
    matches_partial = prefilter("This paper only discusses coral bleaching, nothing marine.")
    goal_14 = next((m for m in matches_partial if m.number == 14), None)
    # "marine" appears in the sentence itself as a negation, so this keyword
    # legitimately still matches -- swap in unrelated text to prove absence.
    matches_absent = prefilter("This paper only discusses coral bleaching in a lab tank.")
    goal_14_absent = next((m for m in matches_absent if m.number == 14), None)
    assert goal_14_absent is None or "marine and coral bleaching" not in goal_14_absent.matched_keywords


def test_empty_text_returns_no_matches():
    assert prefilter("") == []
    assert prefilter("   ") == []


def test_top_n_limits_result_count():
    text = " ".join(kw for g in load_sdg_goals() for kw in g.keywords[:1])
    matches = prefilter(text, top_n=3)
    assert len(matches) <= 3


def test_results_ranked_by_match_count_descending():
    matches = prefilter(
        "vaccination programs, cardiovascular disease, mental health, obesity, "
        "tuberculosis, malaria, hepatitis all discussed in the context of public health."
    )
    counts = [len(m.matched_keywords) for m in matches]
    assert counts == sorted(counts, reverse=True)
