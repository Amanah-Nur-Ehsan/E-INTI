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
import threading
import uuid
from collections import namedtuple

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import ReferencePaper

log = get_logger(__name__)

EMBEDDING_DIM = 768
MAX_TOKENS = 512
_service: "EmbeddingService | None" = None
_service_lock = threading.Lock()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def mark_embedding_stale(reference: ReferencePaper) -> None:
    """Call this whenever a reference's embedded text (title, abstract, or
    keywords) changes. `content_hash IS NULL` is `embed_pending_references`'s
    exact "needs (re-)embedding" signal -- see its docstring. Writers that
    fill in an abstract without calling this leave the row silently
    unembedded, or worse, embedded but stale.
    """
    reference.content_hash = None


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

        from app.core.device import local_inference

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
            # Held per batch, not around the whole loop: a long draft must
            # not lock out another analysis for its entire encode.
            with local_inference(), torch.inference_mode():
                output = self._model(**encoded)
            # SPECTER2 convention: the CLS token is the document vector.
            cls = output.last_hidden_state[:, 0, :]
            cls = torch.nn.functional.normalize(cls, p=2, dim=1)
            vectors.append(cls.detach().to("cpu").float().numpy())

        return np.vstack(vectors)

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


def get_embedding_service() -> EmbeddingService:
    """Process-wide singleton, double-checked so concurrent worker threads
    can't both start loading several hundred MB of model weights."""
    global _service
    if _service is None:
        with _service_lock:
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


_TextFields = namedtuple("_TextFields", ["title", "abstract", "author_keywords", "index_keywords"])


def claim_embedding_text(claim_text: str, context: str | None = None) -> str:
    """Queries use the same encoder; context sharpens an otherwise terse claim."""
    return context.strip() if context and context.strip() else claim_text


def embed_pending_references(session: Session, limit: int | None = None) -> dict:
    """Embed library references whose embedded text has changed.

    `content_hash IS NULL` is the authoritative "needs (re-)embedding"
    signal, set by `mark_embedding_stale` whenever a writer changes the
    title/abstract/keywords a reference is embedded from -- filtering on it
    in SQL (rather than testing "does the hash match" in Python after the
    fact) is what makes `limit` actually bound the *work performed*, not
    just the candidate page size.

    A previous version filtered only `abstract IS NOT NULL` and skipped
    already-current rows in Python after LIMIT was applied. With a small
    `limit`, that meant the same oldest N rows were re-read, found current,
    and skipped -- forever, without ever reaching the rows that actually
    needed embedding. Filtering in SQL fixes that: a skip in the loop below
    is now only reachable if a hash was computed differently than expected
    (a genuine bug elsewhere), not the normal case.

    Runs on the library's own schedule (POST /library/refresh), same as
    enrichment -- embedding cost belongs to the paper, not to whichever
    draft happens to cite it.

    Selects specific columns rather than full ORM entities so a run over
    the whole library doesn't pull every row's 768-float vector just to
    test whether it's already set -- at several thousand rows that's
    tens of megabytes moved for a boolean check.
    """
    counts = {"embedded": 0, "skipped": 0, "no_abstract": 0, "remaining": 0}

    counts["no_abstract"] = session.execute(
        select(func.count()).select_from(ReferencePaper).where(ReferencePaper.abstract.is_(None))
    ).scalar_one()

    pending_filter = (
        ReferencePaper.abstract.isnot(None),
        ReferencePaper.content_hash.is_(None),
    )

    def _count_remaining() -> int:
        return session.execute(
            select(func.count()).select_from(ReferencePaper).where(*pending_filter)
        ).scalar_one()

    query = (
        select(
            ReferencePaper.id,
            ReferencePaper.title,
            ReferencePaper.abstract,
            ReferencePaper.author_keywords,
            ReferencePaper.index_keywords,
            ReferencePaper.content_hash,
            ReferencePaper.embedding.isnot(None),
        )
        .where(*pending_filter)
        .order_by(ReferencePaper.created_at)
    )
    if limit is not None:
        query = query.limit(limit)
    rows = session.execute(query).all()
    if not rows:
        counts["remaining"] = _count_remaining()
        return counts

    service = get_embedding_service()
    separator = "[SEP]" if service.settings.embedding_fake else service.separator

    pending: list[tuple[uuid.UUID, str, str]] = []
    for ref_id, title, abstract, author_kw, index_kw, existing_hash, has_embedding in rows:
        text = reference_embedding_text(
            _TextFields(title, abstract, author_kw, index_kw), separator
        )
        digest = content_hash(text)
        if has_embedding and existing_hash == digest:
            counts["skipped"] += 1
            continue
        pending.append((ref_id, text, digest))

    batch_size = 16
    for start in range(0, len(pending), batch_size):
        chunk = pending[start : start + batch_size]
        vectors = service.encode([text for _, text, _ in chunk])
        for (ref_id, _text, digest), vector in zip(chunk, vectors, strict=True):
            reference = session.get(ReferencePaper, ref_id)
            reference.embedding = vector.tolist()
            reference.content_hash = digest
            reference.embedding_model = service.model_revision
            counts["embedded"] += 1
        session.commit()

    counts["remaining"] = _count_remaining()
    return counts
