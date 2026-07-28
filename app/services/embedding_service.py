"""SPECTER2 document embeddings.

SPECTER2 is the base encoder *plus* the `allenai/specter2` proximity
adapter — loading the base weights alone (as plain sentence-transformers
does) drops the part that makes it good at retrieval, so the adapters
library is used here. Set EMBEDDING_USE_ADAPTER=false to fall back to the
bare base model if the adapter ever fails to load.

The model is loaded lazily, once per worker process; the API process
never imports torch.
"""

import hashlib
import uuid

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import ReferencePaper

log = get_logger(__name__)

EMBEDDING_DIM = 768
MAX_TOKENS = 512
_service: "EmbeddingService | None" = None


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._model = None
        self._tokenizer = None
        self._device: str | None = None
        self.model_revision = self.settings.embedding_model + (
            "+proximity" if self.settings.embedding_use_adapter else ""
        )

    def _load(self) -> None:
        if self._model is not None:
            return

        from adapters import AutoAdapterModel
        from transformers import AutoTokenizer

        from app.core.device import get_device

        self._device = get_device()
        self._tokenizer = AutoTokenizer.from_pretrained(self.settings.embedding_model)
        model = AutoAdapterModel.from_pretrained(self.settings.embedding_model)

        if self.settings.embedding_use_adapter:
            try:
                model.load_adapter(
                    self.settings.embedding_adapter,
                    source="hf",
                    load_as="proximity",
                    set_active=True,
                )
                # load_adapter's set_active does not always survive; setting it
                # explicitly is what actually routes the forward pass through
                # the adapter. Without this the model silently degrades to base.
                model.set_active_adapters("proximity")
                if not model.active_adapters:
                    raise RuntimeError("proximity adapter did not activate")
            except Exception as exc:
                log.warning("specter2_adapter_load_failed", error=str(exc))
                self.model_revision = self.settings.embedding_model

        self._model = model.to(self._device).eval()
        log.info("embedding_model_loaded", model=self.model_revision, device=self._device)

    @property
    def separator(self) -> str:
        if self._tokenizer is None:
            self._load()
        return self._tokenizer.sep_token or "[SEP]"

    def encode(self, texts: list[str], batch_size: int | None = None) -> np.ndarray:
        if not texts:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
        if self.settings.embedding_fake:
            return fake_embed(texts)

        import torch

        self._load()
        if batch_size is None:
            batch_size = 16 if self._device in ("mps", "cuda") else 8

        vectors: list[np.ndarray] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            encoded = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=MAX_TOKENS,
                return_tensors="pt",
            ).to(self._device)
            with torch.inference_mode():
                output = self._model(**encoded)
            # SPECTER2 convention: the CLS token is the document vector.
            cls = output.last_hidden_state[:, 0, :]
            cls = torch.nn.functional.normalize(cls, p=2, dim=1)
            vectors.append(cls.detach().to("cpu").float().numpy())

        return np.vstack(vectors)

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


def get_embedding_service() -> EmbeddingService:
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service


def fake_embed(texts: list[str]) -> np.ndarray:
    """Deterministic stand-in used by tests and CI.

    Hashes tokens into a fixed-width space so that texts sharing vocabulary
    land near each other — enough structure for retrieval assertions without
    downloading a model.
    """
    vectors = np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)
    for row, text in enumerate(texts):
        for token in text.lower().split():
            cleaned = "".join(ch for ch in token if ch.isalnum())
            if not cleaned:
                continue
            index = int(hashlib.md5(cleaned.encode()).hexdigest(), 16) % EMBEDDING_DIM
            vectors[row, index] += 1.0
        norm = np.linalg.norm(vectors[row])
        if norm > 0:
            vectors[row] /= norm
    return vectors


def reference_embedding_text(reference: ReferencePaper, separator: str = "[SEP]") -> str:
    """SPECTER2 input format: title, separator, then the abstract."""
    parts = [reference.title or ""]
    body_parts = []
    if reference.abstract:
        body_parts.append(reference.abstract)
    if reference.author_keywords:
        body_parts.append("Keywords: " + "; ".join(reference.author_keywords))
    if reference.index_keywords:
        body_parts.append("Index terms: " + "; ".join(reference.index_keywords))
    return f"{parts[0]}{separator}{' '.join(body_parts)}".strip()


def claim_embedding_text(claim_text: str, context: str | None = None) -> str:
    """Queries use the same encoder; context sharpens an otherwise terse claim."""
    return context.strip() if context and context.strip() else claim_text


def embed_project_references(session: Session, project_id: uuid.UUID) -> dict:
    """Stage body: embed references whose embedded text has changed.

    The content hash covers title + abstract + keywords, so enrichment
    filling in an abstract invalidates a stale vector automatically.
    """
    references = list(
        session.execute(
            select(ReferencePaper)
            .where(ReferencePaper.project_id == project_id)
            .order_by(ReferencePaper.original_row_number)
        ).scalars()
    )
    if not references:
        return {"embedded": 0, "skipped": 0, "no_abstract": 0}

    service = get_embedding_service()
    separator = "[SEP]" if service.settings.embedding_fake else service.separator

    pending: list[tuple[ReferencePaper, str, str]] = []
    counts = {"embedded": 0, "skipped": 0, "no_abstract": 0}

    for reference in references:
        if not reference.abstract:
            # Nothing meaningful to embed; retrieval will never surface it.
            counts["no_abstract"] += 1
            continue
        text = reference_embedding_text(reference, separator)
        digest = content_hash(text)
        if reference.embedding is not None and reference.content_hash == digest:
            counts["skipped"] += 1
            continue
        pending.append((reference, text, digest))

    batch_size = 16
    for start in range(0, len(pending), batch_size):
        chunk = pending[start : start + batch_size]
        vectors = service.encode([text for _, text, _ in chunk])
        for (reference, _, digest), vector in zip(chunk, vectors, strict=True):
            reference.embedding = vector.tolist()
            reference.content_hash = digest
            reference.embedding_model = service.model_revision
            counts["embedded"] += 1
        session.commit()

    return counts
