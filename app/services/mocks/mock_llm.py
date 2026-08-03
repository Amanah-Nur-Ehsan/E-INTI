"""Deterministic offline LLM stand-in.

Tier 1 re-derives its answer from the same rule prefilter the real pipeline
uses, so batching, index alignment, and schema handling are all genuinely
exercised. Tier 2 decides verdicts from lexical overlap between claim and
abstract, with explicit contradiction cues, so end-to-end expectations are
stable and assertable.
"""

import re

from pydantic import BaseModel

from app.core.logging import get_logger
from app.services.llm_client import Tier

log = get_logger(__name__)

CONTRADICTION_CUES = (
    "no significant",
    "contradicts",
    "fails to replicate",
    "we find no ",
    "does not improve",
)

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "for", "on", "with", "that",
    "this", "these", "those", "is", "are", "was", "were", "be", "been", "by", "as", "at",
    "from", "it", "its", "their", "have", "has", "had", "we", "our", "which", "than",
}


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z]{3,}", text.lower())
        if token not in STOPWORDS
    }


def overlap_ratio(claim: str, document: str) -> float:
    claim_tokens = tokenize(claim)
    if not claim_tokens:
        return 0.0
    return len(claim_tokens & tokenize(document)) / len(claim_tokens)


class MockLLMClient:
    """Implements the LLMClient protocol without any network access."""

    def __init__(self) -> None:
        self.calls: dict[Tier, int] = {Tier.CLASSIFY: 0, Tier.VERIFY: 0}

    def complete_structured(self, *, tier: Tier, system: str, user: str, schema: type[BaseModel]):
        self.calls[tier] = self.calls.get(tier, 0) + 1
        from app.services.sdg_classification_service import SDGPick

        # SDG classification also runs at Tier.CLASSIFY (same cheap model
        # tier as claim classification) but with a distinct schema, so
        # dispatch on schema identity rather than tier alone.
        if schema is SDGPick:
            return self._classify_sdg(user, schema)
        if tier is Tier.CLASSIFY:
            return self._classify(user, schema)
        return self._verify(user, schema)

    # -- Tier 1 -----------------------------------------------------------
    def _classify(self, user: str, schema: type[BaseModel]):
        from app.services.claim_detection_service import PrefilterVerdict, prefilter

        section_match = re.search(r"^Section: (.*)$", user, re.MULTILINE)
        section = section_match.group(1) if section_match else None

        decisions = []
        for idx, sentence in re.findall(r'^(\d+)\. sentence: "(.*)"$', user, re.MULTILINE):
            result = prefilter(sentence, section)
            # Deterministic stand-in for judgement: any rule signal at all is
            # treated as citation-worthy. Threshold chosen so single-signal
            # claims (score 0.20-0.25) pass, as a real classifier would.
            needs = result.verdict is not PrefilterVerdict.SKIP and result.score >= 0.20
            decisions.append(
                {
                    "idx": int(idx),
                    "needs_citation": needs,
                    "claim_type": self._claim_type(result.signals, needs),
                    "claim_text": sentence if needs else "",
                    "reason": f"mock prefilter score {result.score:.2f} ({', '.join(result.signals) or 'no signals'})",
                    "confidence": round(min(0.95, 0.5 + result.score / 2), 2),
                }
            )
        return schema.model_validate({"decisions": decisions})

    # -- SDG classification ------------------------------------------------
    def _classify_sdg(self, user: str, schema: type[BaseModel]):
        """Deterministic stand-in: always pick the first (top-ranked)
        candidate the prefilter shortlisted, and its first matched keyword.
        """
        match = re.search(r"^(\d+): (.+?) -- (.*)$", user, re.MULTILINE)
        if not match:
            return schema.model_validate({"goal_number": 1, "keyword": None})

        goal_number = int(match.group(1))
        keywords_part = match.group(3).strip()
        keyword = None
        if not keywords_part.startswith("(no keyword match"):
            keyword = keywords_part.split(",")[0].strip()
        return schema.model_validate({"goal_number": goal_number, "keyword": keyword})

    @staticmethod
    def _claim_type(signals: list[str], needs: bool) -> str:
        from app.db.models.enums import ClaimType

        if not needs:
            return ClaimType.NO_CITATION_NEEDED
        if "statistic" in signals:
            return ClaimType.STATISTICAL_CLAIM
        if "comparative" in signals:
            return ClaimType.COMPARATIVE_CLAIM
        if "consensus_phrase" in signals:
            return ClaimType.PREVIOUS_RESEARCH
        if "effect_verb" in signals:
            return ClaimType.CAUSAL_CLAIM
        return ClaimType.EMPIRICAL_RESULT

    # -- Tier 2 -----------------------------------------------------------
    def _verify(self, user: str, schema: type[BaseModel]):
        """One claim vs. N numbered candidates, answered in a single call."""
        claim = self._field(user, "CLAIM")

        # Split on the CANDIDATE <n> headers the batch template emits. The
        # first chunk is the claim/context preamble, so it is dropped.
        chunks = re.split(r"^CANDIDATE (\d+)$", user, flags=re.MULTILINE)[1:]
        verdicts = []
        for raw_idx, block in zip(chunks[::2], chunks[1::2], strict=True):
            payload = self._verdict_payload(
                claim=claim,
                title=self._field(block, "TITLE"),
                abstract=self._field(block, "ABSTRACT"),
            )
            verdicts.append({"idx": int(raw_idx), **payload})

        return schema.model_validate({"verdicts": verdicts})

    def _verdict_payload(self, claim: str, title: str, abstract: str) -> dict:
        from app.db.models.enums import Verdict

        if not abstract:
            verdict = Verdict.INSUFFICIENT_EVIDENCE
            evidence = ""
            limitations = "No abstract is available for this reference."
        elif any(cue in abstract.lower() for cue in CONTRADICTION_CUES) and overlap_ratio(
            claim, abstract
        ) >= 0.2:
            verdict = Verdict.CONTRADICTED
            evidence = "The abstract reports a result that runs counter to the claim."
            limitations = "The reference disputes rather than supports the claim."
        else:
            ratio = overlap_ratio(claim, abstract)
            if ratio >= 0.45:
                verdict = Verdict.SUPPORTED
                limitations = ""
            elif ratio >= 0.30:
                verdict = Verdict.PARTIALLY_SUPPORTED
                limitations = "Only part of the claim is addressed by the abstract."
            elif ratio >= 0.15:
                verdict = Verdict.TOPICALLY_RELATED_BUT_NOT_EVIDENCE
                limitations = "The abstract shares topic but does not establish the claim."
            else:
                verdict = Verdict.INSUFFICIENT_EVIDENCE
                limitations = "The abstract does not address the claim."
            evidence = (
                f"The abstract of '{title}' discusses the same subject matter as the claim "
                f"(lexical overlap {ratio:.2f})."
            )

        usage = {
            Verdict.SUPPORTED: "Direct citation",
            Verdict.PARTIALLY_SUPPORTED: "Direct citation",
            Verdict.TOPICALLY_RELATED_BUT_NOT_EVIDENCE: "Background citation",
            Verdict.INSUFFICIENT_EVIDENCE: "Background citation",
            Verdict.CONTRADICTED: "Do not cite",
        }[verdict]

        return {
            "verdict": verdict.value,
            "support_strength": {
                Verdict.SUPPORTED: 0.9,
                Verdict.PARTIALLY_SUPPORTED: 0.6,
                Verdict.TOPICALLY_RELATED_BUT_NOT_EVIDENCE: 0.3,
                Verdict.INSUFFICIENT_EVIDENCE: 0.1,
                Verdict.CONTRADICTED: 0.0,
            }[verdict],
            "supporting_evidence": evidence,
            "limitations": limitations,
            "recommended_usage": usage,
        }

    @staticmethod
    def _field(user: str, label: str) -> str:
        match = re.search(rf"^{label}:\s*(.*?)(?=\n[A-Z]+:|\Z)", user, re.MULTILINE | re.DOTALL)
        return match.group(1).strip() if match else ""
