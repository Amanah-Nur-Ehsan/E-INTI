"""Pre-download SPECTER2 and the cross-encoder into the HuggingFace cache.

Run once after checkout (`make models`) so the first pipeline run isn't
blocked on a few hundred megabytes of downloads.
"""

from app.core.config import get_settings
from app.core.device import get_device


def main() -> None:
    settings = get_settings()
    print(f"device: {get_device()}")

    print(f"loading embedding model: {settings.embedding_model}")
    from app.services.embedding_service import get_embedding_service

    service = get_embedding_service()
    vector = service.encode(["warmup text for the embedding model"])
    print(f"  ok, revision={service.model_revision} dim={vector.shape[1]}")

    print(f"loading reranker: {settings.reranker_model}")
    from app.services.reranking_service import get_reranking_service

    reranker = get_reranking_service()
    scores = reranker.score([("a claim sentence", "a candidate abstract")])
    print(f"  ok, sample score={scores[0]:.4f}")

    print(f"loading spaCy pipeline: {settings.spacy_model}")
    from app.services.draft_parser_service import get_nlp

    doc = get_nlp()("Machine learning improves detection. It does so reliably.")
    print(f"  ok, {len(list(doc.sents))} sentences")


if __name__ == "__main__":
    main()
