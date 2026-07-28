"""Stage 5: final score, display caps, and labels.

The verdict layer always overrides similarity: a paper can be topically
perfect and still fail to support the specific statement, and the caps
below are what keep the percentage from implying otherwise.
"""

from dataclasses import dataclass

from app.db.models.enums import Verdict

W_SEMANTIC = 0.30
W_LEXICAL = 0.15
W_KEYWORD = 0.10
W_RERANKER = 0.30
W_LLM = 0.15

#: Display caps (spec "Hard caps").
CONTRADICTED_CAP = 20.0
MISSING_ABSTRACT_CAP = 45.0

LABEL_STRONG = "Strong recommendation"
LABEL_RECOMMENDED = "Recommended"
LABEL_POSSIBLE = "Possible reference"
LABEL_WEAK = "Weak match"
LABEL_DO_NOT = "Do not recommend"
LABEL_CANNOT_VERIFY = "Cannot verify"


@dataclass
class ScoreBreakdown:
    semantic_similarity: float
    lexical_similarity: float
    keyword_overlap: float
    reranker_score: float
    llm_support_score: float | None
    final_score: float
    score_percentage: float
    label: str

    def as_dict(self) -> dict:
        return {
            "semantic_similarity": round(self.semantic_similarity, 4),
            "lexical_similarity": round(self.lexical_similarity, 4),
            "keyword_overlap": round(self.keyword_overlap, 4),
            "reranker_score": round(self.reranker_score, 4),
            "llm_support_score": (
                None if self.llm_support_score is None else round(self.llm_support_score, 4)
            ),
        }


def label_for(percentage: float, verdict: Verdict, has_abstract: bool) -> str:
    """Map a percentage to a display band, with the verdict overriding it.

    A high similarity score means the paper is *about* the same thing, which
    is not the same as it being evidence for the claim. The ceilings below
    keep the label honest when the verifier disagreed with the similarity.
    """
    if not has_abstract:
        return LABEL_CANNOT_VERIFY

    if percentage >= 85:
        label = LABEL_STRONG
    elif percentage >= 70:
        label = LABEL_RECOMMENDED
    elif percentage >= 50:
        label = LABEL_POSSIBLE
    elif percentage >= 30:
        label = LABEL_WEAK
    else:
        label = LABEL_DO_NOT

    if verdict is Verdict.TOPICALLY_RELATED_BUT_NOT_EVIDENCE and label == LABEL_STRONG:
        # Spec: a topical match must never read as a strong recommendation.
        return LABEL_RECOMMENDED
    if verdict in (Verdict.INSUFFICIENT_EVIDENCE, Verdict.SKIPPED) and label in (
        LABEL_STRONG,
        LABEL_RECOMMENDED,
    ):
        # The verifier found no support at all (or could not run). Presenting
        # that as "Recommended" on the strength of topical similarity is the
        # false-support failure the pipeline exists to prevent.
        return LABEL_POSSIBLE
    return label


def compute_score(
    *,
    semantic_similarity: float,
    lexical_similarity: float,
    keyword_overlap: float,
    reranker_score: float,
    llm_support_score: float | None,
    verdict: Verdict,
    has_abstract: bool,
) -> ScoreBreakdown:
    """Weighted blend, then verdict-driven caps.

    When verification could not run, `llm_support_score` is None: its weight
    is redistributed across the remaining terms rather than scored as zero,
    which would punish a candidate for an infrastructure failure.
    """
    weighted = (
        W_SEMANTIC * semantic_similarity
        + W_LEXICAL * lexical_similarity
        + W_KEYWORD * keyword_overlap
        + W_RERANKER * reranker_score
    )
    if llm_support_score is None:
        total_weight = W_SEMANTIC + W_LEXICAL + W_KEYWORD + W_RERANKER
        final = weighted / total_weight
    else:
        final = weighted + W_LLM * llm_support_score

    final = max(0.0, min(1.0, final))
    percentage = round(final * 100, 1)

    if verdict is Verdict.CONTRADICTED:
        percentage = min(percentage, CONTRADICTED_CAP)
    if not has_abstract:
        percentage = min(percentage, MISSING_ABSTRACT_CAP)

    return ScoreBreakdown(
        semantic_similarity=semantic_similarity,
        lexical_similarity=lexical_similarity,
        keyword_overlap=keyword_overlap,
        reranker_score=reranker_score,
        llm_support_score=llm_support_score,
        final_score=final,
        score_percentage=percentage,
        label=label_for(percentage, verdict, has_abstract),
    )
