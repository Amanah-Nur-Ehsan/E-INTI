import pytest

from app.db.models.enums import SUPPORT_SCORE, Verdict
from app.services.scoring import (
    CONTRADICTED_CAP,
    LABEL_CANNOT_VERIFY,
    LABEL_RECOMMENDED,
    LABEL_STRONG,
    MISSING_ABSTRACT_CAP,
    compute_score,
)


def score(**overrides):
    params = dict(
        semantic_similarity=0.9,
        lexical_similarity=0.8,
        keyword_overlap=0.7,
        reranker_score=0.9,
        llm_support_score=1.0,
        verdict=Verdict.SUPPORTED,
        has_abstract=True,
    )
    params.update(overrides)
    return compute_score(**params)


def test_weights_match_the_specified_blend():
    result = score()
    expected = 0.30 * 0.9 + 0.15 * 0.8 + 0.10 * 0.7 + 0.30 * 0.9 + 0.15 * 1.0
    assert result.final_score == pytest.approx(expected)
    assert result.score_percentage == pytest.approx(round(expected * 100, 1))


def test_support_score_mapping_matches_spec():
    assert SUPPORT_SCORE[Verdict.SUPPORTED] == 1.00
    assert SUPPORT_SCORE[Verdict.PARTIALLY_SUPPORTED] == 0.65
    assert SUPPORT_SCORE[Verdict.TOPICALLY_RELATED_BUT_NOT_EVIDENCE] == 0.35
    assert SUPPORT_SCORE[Verdict.INSUFFICIENT_EVIDENCE] == 0.15
    assert SUPPORT_SCORE[Verdict.CONTRADICTED] == 0.00


def test_contradicted_is_capped_at_20_percent():
    result = score(verdict=Verdict.CONTRADICTED, llm_support_score=0.0)
    assert result.score_percentage <= CONTRADICTED_CAP


def test_contradicted_cap_applies_even_with_perfect_similarity():
    result = score(
        semantic_similarity=1.0,
        lexical_similarity=1.0,
        keyword_overlap=1.0,
        reranker_score=1.0,
        llm_support_score=0.0,
        verdict=Verdict.CONTRADICTED,
    )
    assert result.score_percentage == CONTRADICTED_CAP


def test_missing_abstract_is_capped_and_labelled_cannot_verify():
    result = score(
        verdict=Verdict.INSUFFICIENT_EVIDENCE,
        llm_support_score=SUPPORT_SCORE[Verdict.INSUFFICIENT_EVIDENCE],
        has_abstract=False,
    )
    assert result.score_percentage <= MISSING_ABSTRACT_CAP
    assert result.label == LABEL_CANNOT_VERIFY


def test_topical_match_never_reads_as_strong():
    result = score(
        verdict=Verdict.TOPICALLY_RELATED_BUT_NOT_EVIDENCE,
        llm_support_score=SUPPORT_SCORE[Verdict.TOPICALLY_RELATED_BUT_NOT_EVIDENCE],
        semantic_similarity=1.0,
        lexical_similarity=1.0,
        keyword_overlap=1.0,
        reranker_score=1.0,
    )
    assert result.score_percentage >= 85
    assert result.label == LABEL_RECOMMENDED


def test_strong_label_at_85_percent():
    assert score().label in (LABEL_STRONG, LABEL_RECOMMENDED)
    high = score(
        semantic_similarity=1.0, lexical_similarity=1.0, keyword_overlap=1.0, reranker_score=1.0
    )
    assert high.label == LABEL_STRONG


@pytest.mark.parametrize(
    "value,expected",
    [(0.90, "Strong recommendation"), (0.75, "Recommended"), (0.55, "Possible reference"),
     (0.35, "Weak match"), (0.10, "Do not recommend")],
)
def test_label_bands(value, expected):
    result = compute_score(
        semantic_similarity=value,
        lexical_similarity=value,
        keyword_overlap=value,
        reranker_score=value,
        llm_support_score=value,
        verdict=Verdict.SUPPORTED,
        has_abstract=True,
    )
    assert result.label == expected


def test_skipped_verification_redistributes_the_llm_weight():
    """An unavailable verifier must not be scored as zero support."""
    without_llm = score(llm_support_score=None, verdict=Verdict.SKIPPED)
    as_zero = score(llm_support_score=0.0, verdict=Verdict.SKIPPED)
    assert without_llm.final_score > as_zero.final_score

    expected = (0.30 * 0.9 + 0.15 * 0.8 + 0.10 * 0.7 + 0.30 * 0.9) / 0.85
    assert without_llm.final_score == pytest.approx(expected)
    assert without_llm.llm_support_score is None


def test_score_stays_within_bounds():
    assert score(semantic_similarity=5.0).final_score <= 1.0
    assert score(semantic_similarity=-5.0, lexical_similarity=-1, keyword_overlap=-1,
                 reranker_score=-1, llm_support_score=0.0).final_score >= 0.0
