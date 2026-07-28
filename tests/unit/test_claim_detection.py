import pytest

from app.services.claim_detection_service import (
    PrefilterVerdict,
    find_existing_citations,
    prefilter,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Deep learning improves detection [1].", ["[1]"]),
        ("Several methods exist [1, 2].", ["[1, 2]"]),
        ("Prior work covers this [1-4].", ["[1-4]"]),
        ("Prior work covers this [1–4].", ["[1–4]"]),
        ("Blockchain increases transparency (Smith, 2024).", ["(Smith, 2024)"]),
        ("As reported (Smith & Jones, 2024).", ["(Smith & Jones, 2024)"]),
        ("As reported (Smith et al., 2024).", ["(Smith et al., 2024)"]),
        ("Smith et al. (2024) showed the effect.", ["Smith et al. (2024)"]),
        ("Smith and Jones (2024) showed the effect.", ["Smith and Jones (2024)"]),
        ("Hidayat (2023) proposed the framework.", ["Hidayat (2023)"]),
    ],
)
def test_citation_syntax_is_detected(text, expected):
    assert find_existing_citations(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "The results are described in more detail below.",
        "Machine learning improves detection accuracy substantially.",
        "As shown (see Section 2), the effect is stable.",
        "The procedure is described in Figure 3 and Table 2.",
        "Detection rates rose between 2019 and 2024.",
    ],
)
def test_non_citations_are_not_matched(text):
    assert find_existing_citations(text) == []


def test_multiple_citations_in_one_sentence():
    found = find_existing_citations("Two lines of work exist (Smith, 2023; Lee, 2020) and [7].")
    assert "(Smith, 2023; Lee, 2020)" in found
    assert "[7]" in found


@pytest.mark.parametrize(
    "text",
    [
        "Previous research shows that ensemble methods reduce false positive rates markedly.",
        "Deep learning improves the performance of fraud detection systems considerably.",
        "Transformer models outperform traditional approaches compared with earlier baselines.",
    ],
)
def test_claim_like_sentences_are_not_skipped(text):
    assert prefilter(text).verdict is not PrefilterVerdict.SKIP
    assert prefilter(text).score > 0


@pytest.mark.parametrize(
    "text,section",
    [
        ("This study uses a qualitative research design.", "Methodology"),
        ("The next section describes the proposed framework.", "Methodology"),
        ("Table 2 presents the experimental results.", "Results"),
        ("Is this effect stable across datasets?", "Discussion"),
        ("We thank the reviewers.", "Acknowledgments"),
        ("Short sentence.", None),
    ],
)
def test_non_claims_are_skipped(text, section):
    assert prefilter(text, section).verdict is PrefilterVerdict.SKIP


def test_author_contribution_is_penalised():
    result = prefilter("In this paper we propose a method that improves detection accuracy.")
    assert "author_contribution" in result.signals
    assert result.verdict is PrefilterVerdict.SKIP


def test_strong_signal_survives_without_llm():
    result = prefilter(
        "Previous studies show that deep learning improves detection accuracy by 15 percent."
    )
    assert result.verdict is PrefilterVerdict.STRONG
    assert {"consensus_phrase", "reporting_verb", "effect_verb", "statistic"} & set(result.signals)


def test_mock_tier1_alignment_preserves_indices():
    from app.services.claim_detection_service import ClaimBatchDecision
    from app.services.llm_client import Tier
    from app.services.mocks.mock_llm import MockLLMClient

    user = (
        "Draft title: T\nSection: Introduction\n\nSentences:\n"
        '0. sentence: "Previous studies show that deep learning improves detection accuracy."\n'
        '   context: "..."\n'
        '1. sentence: "The next section describes the proposed framework in detail."\n'
        '   context: "..."\n'
    )
    result = MockLLMClient().complete_structured(
        tier=Tier.CLASSIFY, system="s", user=user, schema=ClaimBatchDecision
    )
    by_idx = {d.idx: d for d in result.decisions}
    assert by_idx[0].needs_citation is True
    assert by_idx[1].needs_citation is False
