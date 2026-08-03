"""Stages 1-3 are batched across claims: one embedding call and one
cross-encoder pass for the whole draft, not one of each per claim.

The batching only pays off if it is real, and it is only safe if the
per-claim results are unchanged -- so this asserts both: the call counts,
and that the persisted recommendations are identical to what the
one-claim-at-a-time path produces.
"""

import pytest

from app.db.models import CitationRecommendation, Claim
from app.services.claim_detection_service import detect_and_store_claims
from app.services.draft_parser_service import parse_and_store_draft
from app.services.recommendation_pipeline import (
    LibraryCorpus,
    recommend_for_claim,
    recommend_for_draft,
)

pytestmark = pytest.mark.integration


class _SpyEmbedder:
    def __init__(self, inner):
        self._inner = inner
        self.encode_calls = 0
        self.texts_seen = 0

    def encode(self, texts, batch_size=None):
        self.encode_calls += 1
        self.texts_seen += len(texts)
        return self._inner.encode(texts, batch_size)

    def encode_one(self, text):
        return self.encode([text])[0]

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _SpyReranker:
    def __init__(self, inner):
        self._inner = inner
        self.score_calls = 0
        self.pairs_seen = 0

    def score(self, pairs):
        self.score_calls += 1
        self.pairs_seen += len(pairs)
        return self._inner.score(pairs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _prepare_claims(db_session, draft_id) -> list[Claim]:
    parse_and_store_draft(db_session, draft_id)
    detect_and_store_claims(db_session, draft_id)
    return list(
        db_session.query(Claim)
        .filter(Claim.draft_id == draft_id, Claim.needs_citation.is_(True))
        .order_by(Claim.char_start)
    )


def _install_spies(monkeypatch):
    from app.services.embedding_service import get_embedding_service
    from app.services.reranking_service import get_reranking_service

    embedder = _SpyEmbedder(get_embedding_service())
    reranker = _SpyReranker(get_reranking_service())
    monkeypatch.setattr(
        "app.services.recommendation_pipeline.get_embedding_service", lambda: embedder
    )
    monkeypatch.setattr(
        "app.services.recommendation_pipeline.get_reranking_service", lambda: reranker
    )
    return embedder, reranker


def test_whole_draft_takes_one_encode_and_one_rerank_pass(db_session, seeded_draft, monkeypatch):
    import uuid as _uuid

    draft_id = _uuid.UUID(seeded_draft)
    claims = _prepare_claims(db_session, draft_id)
    assert len(claims) > 1, "fixture must produce several claims for batching to mean anything"

    embedder, reranker = _install_spies(monkeypatch)
    result = recommend_for_draft(db_session, draft_id)

    assert result["claims_processed"] == len(claims)
    # One encode for every claim's query vector, not one per claim.
    assert embedder.encode_calls == 1
    assert embedder.texts_seen == len(claims)
    # The fixture library is small enough to fit one rerank batch.
    assert reranker.score_calls == 1
    assert reranker.pairs_seen > len(claims)


def test_batched_results_match_the_per_claim_path(db_session, seeded_draft, monkeypatch):
    """The batching must be a pure scheduling change: same rows, same
    ranks, same scores as running each claim on its own.
    """
    import uuid as _uuid

    draft_id = _uuid.UUID(seeded_draft)
    claims = _prepare_claims(db_session, draft_id)

    recommend_for_draft(db_session, draft_id)
    batched = {
        (r.claim_id, r.rank): (r.reference_id, round(r.score_percentage, 6))
        for r in db_session.query(CitationRecommendation).all()
    }
    assert batched, "expected the batched run to persist recommendations"

    # Re-run claim by claim through the single-claim wrapper; each call
    # replaces that claim's rows, so the table ends up rebuilt the slow way.
    corpus = LibraryCorpus(db_session)
    for claim in claims:
        recommend_for_claim(db_session, claim, corpus)

    per_claim = {
        (r.claim_id, r.rank): (r.reference_id, round(r.score_percentage, 6))
        for r in db_session.query(CitationRecommendation).all()
    }

    assert per_claim == batched
