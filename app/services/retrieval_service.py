"""Stages 1-2: pgvector retrieval and hybrid pre-ranking.

Recall matters more than precision here — the cross-encoder and the
verifier downstream do the pruning. The BM25 corpus is built once per
project per run rather than per claim.
"""

import re
import uuid
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging import get_logger

log = get_logger(__name__)

RETRIEVAL_LIMIT = 20
RERANK_LIMIT = 10

#: Hybrid pre-ranking weights (spec "Stage 3: Hybrid pre-ranking").
W_SEMANTIC = 0.55
W_BM25 = 0.20
W_KEYWORD = 0.15
W_FIELD = 0.10

_TOKEN_RE = re.compile(r"[a-z][a-z0-9\-]{2,}")
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has",
    "have", "their", "which", "than", "these", "those", "our", "not", "but", "can",
    "its", "into", "such", "when", "they", "them", "been", "also", "more", "most",
}


def tokenize(value: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((value or "").lower()) if t not in STOPWORDS]


@dataclass
class Candidate:
    reference_id: uuid.UUID
    title: str
    abstract: str | None
    author_keywords: list[str] = field(default_factory=list)
    index_keywords: list[str] = field(default_factory=list)
    field_of_study: str | None = None
    year: int | None = None
    source_title: str | None = None
    doi: str | None = None

    semantic_similarity: float = 0.0
    lexical_similarity: float = 0.0
    keyword_overlap: float = 0.0
    field_match: float = 0.0
    prerank_score: float = 0.0

    @property
    def has_abstract(self) -> bool:
        return bool(self.abstract and self.abstract.strip())

    def searchable_text(self) -> str:
        parts = [self.title or "", self.abstract or ""]
        parts.extend(self.author_keywords or [])
        parts.extend(self.index_keywords or [])
        return " ".join(parts)


class ProjectCorpus:
    """BM25 index over every embedded reference in the project.

    Built once per run so IDF reflects the whole corpus, not the 20 rows a
    single claim happened to retrieve.
    """

    def __init__(self, session: Session, project_id: uuid.UUID):
        rows = session.execute(
            text(
                "SELECT id, title, abstract, author_keywords, index_keywords "
                "FROM reference_papers "
                "WHERE project_id = :pid AND embedding IS NOT NULL"
            ),
            {"pid": str(project_id)},
        ).all()

        self.reference_ids = [row[0] for row in rows]
        documents = []
        for _, title, abstract, author_keywords, index_keywords in rows:
            blob = " ".join(
                filter(
                    None,
                    [
                        title or "",
                        abstract or "",
                        " ".join(author_keywords or []),
                        " ".join(index_keywords or []),
                    ],
                )
            )
            documents.append(tokenize(blob))

        self._index_by_id = {rid: i for i, rid in enumerate(self.reference_ids)}
        self._bm25 = None
        if documents:
            from rank_bm25 import BM25Okapi

            self._bm25 = BM25Okapi(documents)

    def scores_for(self, query: str, reference_ids: list[uuid.UUID]) -> dict[uuid.UUID, float]:
        """Min-max normalized BM25 scores, restricted to the given candidates."""
        if self._bm25 is None or not reference_ids:
            return {rid: 0.0 for rid in reference_ids}

        all_scores = self._bm25.get_scores(tokenize(query))
        subset = {
            rid: float(all_scores[self._index_by_id[rid]])
            for rid in reference_ids
            if rid in self._index_by_id
        }
        if not subset:
            return {rid: 0.0 for rid in reference_ids}

        lowest, highest = min(subset.values()), max(subset.values())
        span = highest - lowest
        if span <= 0:
            return {rid: (1.0 if highest > 0 else 0.0) for rid in reference_ids}
        return {rid: (subset.get(rid, lowest) - lowest) / span for rid in reference_ids}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def keyword_overlap(claim_keywords: list[str], candidate: Candidate) -> float:
    claim_tokens = set()
    for keyword in claim_keywords or []:
        claim_tokens.update(tokenize(keyword))

    candidate_tokens = set()
    for keyword in (candidate.author_keywords or []) + (candidate.index_keywords or []):
        candidate_tokens.update(tokenize(keyword))
    candidate_tokens.update(tokenize(candidate.title or ""))

    return jaccard(claim_tokens, candidate_tokens)


def field_match(project_field: str | None, candidate: Candidate) -> float:
    if not project_field or not candidate.field_of_study:
        return 0.0
    left, right = set(tokenize(project_field)), set(tokenize(candidate.field_of_study))
    if not left or not right:
        return 0.0
    return 1.0 if len(left & right) / len(left) >= 0.5 else 0.0


def vector_search(
    session: Session,
    project_id: uuid.UUID,
    query_vector: np.ndarray,
    limit: int = RETRIEVAL_LIMIT,
) -> list[Candidate]:
    rows = session.execute(
        text(
            "SELECT id, title, abstract, author_keywords, index_keywords, field_of_study, "
            "       year, source_title, doi, "
            "       1 - (embedding <=> CAST(:v AS vector)) AS semantic_similarity "
            "FROM reference_papers "
            "WHERE project_id = :pid AND embedding IS NOT NULL "
            "ORDER BY embedding <=> CAST(:v AS vector) "
            "LIMIT :k"
        ),
        {"v": str(query_vector.tolist()), "pid": str(project_id), "k": limit},
    ).all()

    return [
        Candidate(
            reference_id=row[0],
            title=row[1],
            abstract=row[2],
            author_keywords=list(row[3] or []),
            index_keywords=list(row[4] or []),
            field_of_study=row[5],
            year=row[6],
            source_title=row[7],
            doi=row[8],
            semantic_similarity=float(row[9]),
        )
        for row in rows
    ]


def prerank(
    candidates: list[Candidate],
    corpus: ProjectCorpus,
    query: str,
    claim_keywords: list[str],
    project_field: str | None,
    limit: int = RERANK_LIMIT,
) -> list[Candidate]:
    if not candidates:
        return []

    bm25 = corpus.scores_for(query, [c.reference_id for c in candidates])
    for candidate in candidates:
        candidate.lexical_similarity = bm25.get(candidate.reference_id, 0.0)
        candidate.keyword_overlap = keyword_overlap(claim_keywords, candidate)
        candidate.field_match = field_match(project_field, candidate)
        candidate.prerank_score = (
            W_SEMANTIC * candidate.semantic_similarity
            + W_BM25 * candidate.lexical_similarity
            + W_KEYWORD * candidate.keyword_overlap
            + W_FIELD * candidate.field_match
        )

    candidates.sort(key=lambda c: c.prerank_score, reverse=True)
    return candidates[:limit]
