"""Stage 3: local cross-encoder reranking.

The cross-encoder sees the claim and the candidate abstract together, which
catches relevance the bi-encoder's independent embeddings miss. ~22M
parameters, so it is cheap enough to run on CPU in production.
"""

import math

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

MAX_ABSTRACT_CHARS = 1500
_service: "RerankingService | None" = None


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


class RerankingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        from sentence_transformers import CrossEncoder

        from app.core.device import get_device

        device = get_device()
        self._model = CrossEncoder(self.settings.reranker_model, device=device, max_length=512)
        log.info("reranker_loaded", model=self.settings.reranker_model, device=device)

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Return relevance in [0, 1] for each (query, document) pair."""
        if not pairs:
            return []
        if self.settings.reranker_fake:
            return [fake_score(query, document) for query, document in pairs]

        self._load()
        raw = self._model.predict(pairs, show_progress_bar=False)
        # ms-marco cross-encoders emit unbounded logits; squash to [0, 1].
        return [_sigmoid(float(value)) for value in raw]


def get_reranking_service() -> RerankingService:
    global _service
    if _service is None:
        _service = RerankingService()
    return _service


def fake_score(query: str, document: str) -> float:
    """Deterministic token-overlap stand-in used by tests and CI."""
    from app.services.retrieval_service import tokenize

    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    return len(query_tokens & set(tokenize(document))) / len(query_tokens)


def build_pair(claim_context: str, title: str, abstract: str | None) -> tuple[str, str]:
    document = f"{title}. {(abstract or '')[:MAX_ABSTRACT_CHARS]}".strip()
    return claim_context, document
