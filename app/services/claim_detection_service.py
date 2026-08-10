"""Three-layer claim detection.

Layer 3 (existing citations) runs first — a sentence that already carries a
citation is recorded as such and is not re-litigated. Layer 1 is a cheap
rule prefilter that discards obvious non-claims before spending tokens.
Layer 2 asks the Tier-1 LLM about everything the rules were unsure of, in
batches, with the neighbouring sentences as context.
"""

import hashlib
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from functools import partial

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Claim, Draft, LLMClassificationCache
from app.db.models.enums import ClaimType, DetectionMethod, ExistingCitationStatus
from app.services.draft_parser_service import Sentence, local_context
from app.services.llm_client import Tier, get_llm_client

log = get_logger(__name__)

# --------------------------------------------------------------------------
# Layer 3: existing citation syntax
# --------------------------------------------------------------------------

CITATION_PATTERNS = [
    # [1], [1, 2], [1-3], [1–4]
    re.compile(r"\[\s*\d+(?:\s*[,;]\s*\d+)*(?:\s*[–—-]\s*\d+)?\s*\]"),
    # (Smith, 2024), (Smith & Doe, 2024; Lee, 2020), (Smith et al., 2024)
    re.compile(
        r"\(\s*[A-Z][A-Za-z\-']+"
        r"(?:\s+(?:et\s+al\.?|and|&)\s*[A-Z]?[A-Za-z\-']*)*"
        r"\s*,\s*\d{4}[a-z]?"
        r"(?:\s*;\s*[^()]{0,80}?,\s*\d{4}[a-z]?)*\s*\)"
    ),
    # Smith et al. (2024) / Smith and Doe (2024)
    re.compile(
        r"\b[A-Z][A-Za-z\-']+\s+(?:et\s+al\.?|and\s+[A-Z][A-Za-z\-']+)\s*\(\s*\d{4}[a-z]?\s*\)"
    ),
    # Smith (2024)
    re.compile(r"\b[A-Z][A-Za-z\-']+\s*\(\s*\d{4}[a-z]?\s*\)"),
]

#: Parenthesised cross-references that look like citations but are not.
_NOT_A_CITATION = re.compile(
    r"\((?:see|cf\.?|in|from|as in)\s+(?:Section|Sec\.|Chapter|Fig\.|Figure|Table|Appendix|Eq\.)",
    re.IGNORECASE,
)


def find_existing_citations(text: str) -> list[str]:
    if _NOT_A_CITATION.search(text):
        text = _NOT_A_CITATION.sub("(", text)

    # Patterns are ordered broadest first; a later, narrower pattern must not
    # re-report the tail of a match already claimed (e.g. "Jones (2024)" inside
    # "Smith and Jones (2024)").
    spans: list[tuple[int, int]] = []
    found: list[str] = []
    for pattern in CITATION_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start >= s and end <= e for s, e in spans):
                continue
            spans.append((start, end))
            found.append(match.group(0))
    return found


# --------------------------------------------------------------------------
# Layer 1: rule prefilter
# --------------------------------------------------------------------------


class PrefilterVerdict(StrEnum):
    SKIP = "SKIP"
    SEND_TO_LLM = "SEND_TO_LLM"
    STRONG = "STRONG"


REPORTING_VERBS = re.compile(
    r"\b(?:show[ns]?|showed|demonstrat\w+|suggest\w*|indicat\w+|report\w*|reveal\w*|find[s]?|"
    r"found|observ\w+|conclude[ds]?|argue[ds]?|establish\w*|confirm\w*)\b",
    re.IGNORECASE,
)
CONSENSUS_PHRASES = re.compile(
    r"\b(?:previous (?:research|studies|work)|prior (?:studies|work|research)|several studies|"
    r"many studies|has been shown|have been shown|it is (?:well )?known|widely used|"
    r"widely adopted|according to|the literature|state of the art|commonly used|"
    r"studies (?:show|report|indicate)|research (?:shows|indicates))\b",
    re.IGNORECASE,
)
EFFECT_VERBS = re.compile(
    r"\b(?:improve[sd]?|increase[sd]?|decrease[sd]?|reduce[sd]?|enhance[sd]?|outperform\w*|"
    r"degrade[sd]?|affect[sd]?|cause[sd]?|lead[s]? to|contribute[sd]? to|result[s]? in|lose[s]?)\b",
    re.IGNORECASE,
)
COMPARATIVES = re.compile(
    r"\b(?:more|less|higher|lower|better|worse|faster|slower|greater|fewer)\b\s+\w+\s+than\b"
    r"|\b(?:compared (?:to|with)|relative to|in contrast to)\b",
    re.IGNORECASE,
)
STATISTICS = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|percent)|p\s*[<>=]\s*0?\.\d+|\bn\s*=\s*\d+", re.IGNORECASE
)
FIRST_PERSON_CONTRIBUTION = re.compile(
    r"\b(?:in this (?:paper|study|section|work|article)|this (?:paper|study|section|article) "
    r"(?:presents|describes|proposes|uses|investigates|examines)|we (?:propose|present|introduce|"
    r"describe|evaluate|use|apply|adopt|report|conduct|do not)|the (?:next|following|remainder) "
    r"(?:section|of))\b",
    re.IGNORECASE,
)
STRUCTURAL_REFERENCE = re.compile(
    r"^(?:table|figure|fig\.|equation|eq\.|algorithm|appendix|section)\s+\d+", re.IGNORECASE
)
NON_CLAIM_SECTIONS = {"references", "acknowledgments", "acknowledgements", "bibliography"}

MIN_TOKENS = 8


@dataclass
class PrefilterResult:
    verdict: PrefilterVerdict
    score: float
    signals: list[str]


def prefilter(text: str, section_title: str | None = None) -> PrefilterResult:
    if section_title and section_title.strip().lower() in NON_CLAIM_SECTIONS:
        return PrefilterResult(PrefilterVerdict.SKIP, 0.0, ["non_claim_section"])
    if len(text.split()) < MIN_TOKENS:
        return PrefilterResult(PrefilterVerdict.SKIP, 0.0, ["too_short"])
    if text.rstrip().endswith("?"):
        return PrefilterResult(PrefilterVerdict.SKIP, 0.0, ["question"])
    if STRUCTURAL_REFERENCE.match(text.strip()):
        return PrefilterResult(PrefilterVerdict.SKIP, 0.0, ["structural_reference"])

    signals: list[str] = []
    score = 0.0
    if CONSENSUS_PHRASES.search(text):
        signals.append("consensus_phrase")
        score += 0.45
    if REPORTING_VERBS.search(text):
        signals.append("reporting_verb")
        score += 0.25
    if EFFECT_VERBS.search(text):
        signals.append("effect_verb")
        score += 0.25
    if COMPARATIVES.search(text):
        signals.append("comparative")
        score += 0.20
    if STATISTICS.search(text):
        signals.append("statistic")
        score += 0.15

    if FIRST_PERSON_CONTRIBUTION.search(text):
        # The authors describing their own work needs no external citation.
        signals.append("author_contribution")
        return PrefilterResult(PrefilterVerdict.SKIP, 0.0, signals)

    score = max(0.0, min(1.0, score))
    # Only the hard exclusions above are dropped outright. Everything else goes
    # to the LLM even with no rule signals — this stage optimizes recall, and a
    # plain factual claim ("Accuracy is misleading when the class is rare")
    # carries none of the surface cues the patterns look for.
    verdict = PrefilterVerdict.STRONG if score >= 0.6 else PrefilterVerdict.SEND_TO_LLM
    return PrefilterResult(verdict, score, signals)


# --------------------------------------------------------------------------
# Layer 2: Tier-1 LLM classification
# --------------------------------------------------------------------------

CLASSIFY_SYSTEM = """You are an academic citation reviewer.

For each numbered sentence, decide whether it makes a verifiable scholarly claim
that should normally be supported by one or more external academic citations.

Sentences describing the authors' own study design, the structure of the paper, or
pointers to tables and figures do NOT need citations. Statements about prior
findings, established facts, empirical results, comparisons, or causal effects DO.

Return JSON only."""

CLASSIFY_USER_TEMPLATE = """Draft title: {title}
Section: {section}

Classify each sentence. Respond with:
{{"decisions": [{{"idx": <int>, "needs_citation": <bool>, "claim_type": "<TYPE>",
"claim_text": "<atomic claim or empty>", "reason": "<short>", "confidence": <0.0-1.0>}}]}}

Valid claim_type values: {claim_types}

Sentences:
{sentences}"""


class ClaimDecision(BaseModel):
    idx: int
    needs_citation: bool
    claim_type: str = ClaimType.NO_CITATION_NEEDED
    claim_text: str = ""
    reason: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ClaimBatchDecision(BaseModel):
    decisions: list[ClaimDecision]


def _normalize_claim_type(value: str, needs_citation: bool) -> str:
    candidate = (value or "").strip().upper().replace(" ", "_")
    if candidate in ClaimType.__members__:
        return candidate
    return ClaimType.GENERAL_BACKGROUND if needs_citation else ClaimType.NO_CITATION_NEEDED


def classify_batch(
    client, batch: list[tuple[int, Sentence, str]], draft_title: str
) -> dict[int, ClaimDecision]:
    """Classify one batch; returns {sentence_index: decision}, empty on LLM failure.

    The prompt numbers sentences 0..n-1 within the batch rather than by their
    position in the draft: models renumber sequentially regardless of what they
    are given, so batch-local numbering is the only mapping that survives a
    batch with gaps (sentences the prefilter already excluded).
    """
    numbered = "\n".join(
        f'{local}. sentence: "{sentence.text}"\n   context: "{context}"'
        for local, (_, sentence, context) in enumerate(batch)
    )
    section = batch[0][1].section_title or "Unknown"
    user = CLASSIFY_USER_TEMPLATE.format(
        title=draft_title,
        section=section,
        claim_types=", ".join(t.value for t in ClaimType),
        sentences=numbered,
    )

    # No try/except here: a batch that fails after every transport retry and
    # the Gemini fallback raises LLMOutputError straight through to the
    # caller. Swallowing it used to return {} for the whole batch -- up to
    # classify_batch_size sentences silently written off as "no citation
    # needed" with nothing visible to the user. PipelineTask.run already
    # catches this, marks the analysis_run FAILED with the message, and lets
    # the user re-trigger it -- now warm-cached for every sentence that
    # already succeeded (see _load_classification_cache below).
    result = client.complete_structured(
        tier=Tier.CLASSIFY,
        system=CLASSIFY_SYSTEM,
        user=user,
        schema=ClaimBatchDecision,
    )

    # Translate batch-local indices back to draft sentence indices, dropping
    # anything out of range rather than letting it land on the wrong sentence.
    decisions: dict[int, ClaimDecision] = {}
    for decision in result.decisions:
        if 0 <= decision.idx < len(batch):
            decisions[batch[decision.idx][0]] = decision
        else:
            log.warning("claim_decision_index_out_of_range", idx=decision.idx, batch=len(batch))
    return decisions


def claim_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _classification_model_name() -> str:
    settings = get_settings()
    return "mock" if settings.llm_mocked else settings.tier1_model


def _load_classification_cache(
    session: Session, sentence_hashes: list[str], model: str
) -> dict[str, ClaimDecision]:
    if not sentence_hashes:
        return {}
    rows = session.execute(
        select(LLMClassificationCache).where(
            LLMClassificationCache.sentence_hash.in_(sentence_hashes),
            LLMClassificationCache.model == model,
        )
    ).scalars()
    return {row.sentence_hash: ClaimDecision(**row.payload) for row in rows}


def _store_classification_cache(
    session: Session, sentence_hash: str, model: str, decision: ClaimDecision
) -> None:
    session.execute(
        pg_insert(LLMClassificationCache)
        .values(
            id=uuid.uuid4(),
            sentence_hash=sentence_hash,
            model=model,
            payload=decision.model_dump(),
        )
        .on_conflict_do_nothing(index_elements=["sentence_hash", "model"])
    )


def extract_keywords(text: str) -> list[str]:
    from app.services.draft_parser_service import get_nlp

    doc = get_nlp()(text)
    keywords: list[str] = []
    for chunk in doc.noun_chunks:
        phrase = " ".join(t.text.lower() for t in chunk if not t.is_stop and t.is_alpha)
        phrase = phrase.strip()
        if len(phrase) > 2 and phrase not in keywords:
            keywords.append(phrase)
    return keywords[:12]


def detect_and_store_claims(session: Session, draft_id: uuid.UUID) -> dict:
    """Stage body: rebuild the claim set for a draft.

    Claims are deleted and recreated so a re-run reflects the current text;
    their recommendations cascade away with them.
    """
    draft = session.get(Draft, draft_id)
    if draft is None:
        raise ValueError(f"Draft {draft_id} not found")
    if not draft.parsed_content:
        raise ValueError(f"Draft {draft_id} has not been parsed")

    sentences = [Sentence(**s) for s in draft.parsed_content.get("sentences", [])]
    if not sentences:
        return {"claims": 0, "needs_citation": 0, "already_cited": 0, "llm_calls": 0}

    blocks = draft.parsed_content.get("blocks", [])
    draft_title = blocks[0]["text"] if blocks else draft.original_filename

    session.execute(delete(Claim).where(Claim.draft_id == draft_id))

    client = get_llm_client()
    to_classify: list[tuple[int, Sentence, str]] = []
    records: dict[int, dict] = {}

    for index, sentence in enumerate(sentences):
        context = local_context(sentences, index)
        record = {
            "sentence": sentence,
            "context": context,
            "citations": find_existing_citations(sentence.text),
            "prefilter": prefilter(sentence.text, sentence.section_title),
            "decision": None,
        }
        records[index] = record

        if record["prefilter"].verdict is not PrefilterVerdict.SKIP:
            to_classify.append((index, sentence, context))

    # Consult the Tier-1 cache before spending any LLM calls. Keyed on the
    # sentence alone (not the batch, which varies between runs, and not the
    # local context, where a neighbour edit would cold-cache an unchanged
    # sentence for negligible benefit) -- so a re-run over an unmodified
    # draft costs zero Tier-1 calls, and an edited draft pays only for the
    # sentences that actually changed.
    model_name = _classification_model_name()
    hash_by_index = {index: claim_hash(sentence.text) for index, sentence, _ in to_classify}
    cached = _load_classification_cache(session, list(hash_by_index.values()), model_name)

    uncached: list[tuple[int, Sentence, str]] = []
    for index, sentence, context in to_classify:
        decision = cached.get(hash_by_index[index])
        if decision is not None:
            records[index]["decision"] = decision
        else:
            uncached.append((index, sentence, context))

    settings = get_settings()
    batch_size = settings.classify_batch_size
    batches = [uncached[start : start + batch_size] for start in range(0, len(uncached), batch_size)]
    llm_calls = len(batches)

    # classify_batch takes no session and touches no shared mutable state --
    # only the LLM call itself -- so batches are independent and safe to
    # run concurrently. pool.map keeps results index-aligned with `batches`
    # and re-raises the first LLMOutputError in submission order, so a
    # failure still fails the whole stage exactly as the serial loop did
    # (see classify_batch's docstring for why that's deliberate).
    if batches:
        call = partial(classify_batch, client, draft_title=draft_title)
        with ThreadPoolExecutor(max_workers=min(settings.llm_max_concurrency, len(batches))) as pool:
            results = list(pool.map(call, batches))
    else:
        results = []

    for decisions in results:
        for idx, decision in decisions.items():
            _store_classification_cache(session, hash_by_index[idx], model_name, decision)
            if idx in records:
                records[idx]["decision"] = decision

    counts = {"claims": 0, "needs_citation": 0, "already_cited": 0, "llm_calls": llm_calls}

    for record in records.values():
        sentence: Sentence = record["sentence"]
        result: PrefilterResult = record["prefilter"]
        decision: ClaimDecision | None = record["decision"]
        citations: list[str] = record["citations"]

        if decision is not None:
            needs_citation = decision.needs_citation
            confidence = decision.confidence
            method = DetectionMethod.LLM
            claim_type = _normalize_claim_type(decision.claim_type, needs_citation)
            claim_text = decision.claim_text.strip() or sentence.text
        elif result.verdict is PrefilterVerdict.STRONG:
            # LLM unavailable: trust the strong rule signal rather than dropping it.
            needs_citation = True
            confidence = result.score
            method = DetectionMethod.RULE
            claim_type = ClaimType.GENERAL_BACKGROUND
            claim_text = sentence.text
        else:
            needs_citation = False
            confidence = result.score
            method = DetectionMethod.RULE
            claim_type = ClaimType.NO_CITATION_NEEDED
            claim_text = sentence.text

        if not needs_citation and not citations:
            # Nothing to review and nothing to recommend: don't store a row.
            continue

        if citations:
            citation_status = ExistingCitationStatus.CITATION_EXISTS_NOT_CHECKED
            counts["already_cited"] += 1
        else:
            citation_status = ExistingCitationStatus.NO_CITATION_FOUND

        session.add(
            Claim(
                draft_id=draft_id,
                section_title=sentence.section_title,
                paragraph_index=sentence.paragraph_index,
                sentence_index=sentence.sentence_index,
                char_start=sentence.char_start,
                char_end=sentence.char_end,
                sentence_text=sentence.text,
                local_context=record["context"],
                claim_text=claim_text,
                needs_citation=needs_citation,
                claim_type=claim_type,
                claim_confidence=confidence,
                detection_method=method,
                existing_citation_text="; ".join(citations) or None,
                existing_citation_status=citation_status,
                # Hash the source sentence, not the LLM's paraphrase
                # (claim_text): the paraphrase can drift between runs even
                # at temperature 0.0, which would silently invalidate the
                # verification cache. The sentence is stable.
                claim_hash=claim_hash(sentence.text),
                keywords=extract_keywords(sentence.text),
            )
        )
        counts["claims"] += 1
        if needs_citation:
            counts["needs_citation"] += 1

    session.commit()
    return counts


def claims_for_draft(session: Session, draft_id: uuid.UUID) -> list[Claim]:
    return list(
        session.execute(
            select(Claim).where(Claim.draft_id == draft_id).order_by(Claim.char_start)
        ).scalars()
    )
