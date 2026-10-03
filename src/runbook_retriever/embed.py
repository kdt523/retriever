"""Load sentence-transformers models and encode queries / corpus, with a disk cache.

Every model has exactly one query prefix, looked up here. BGE models get the shared
``QUERY_PREFIX``; models trained without an instruction (MiniLM) get none, so baselines
are not handicapped by someone else's prompt.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from runbook_retriever.config import MAX_SEQ_LENGTH, QUERY_PREFIX
from runbook_retriever.corpus import Chunk

log = logging.getLogger(__name__)

Matrix = npt.NDArray[np.float32]

_NO_PREFIX_MODELS = ("sentence-transformers/all-MiniLM-L6-v2",)


def query_prefix(model_name: str) -> str:
    """Query instruction for ``model_name``: QUERY_PREFIX for BGE and our tuned models."""
    return "" if model_name in _NO_PREFIX_MODELS else QUERY_PREFIX


def load_model(model_name: str, device: str | None = None) -> Any:
    """SentenceTransformer in fp16 on GPU when available, capped at MAX_SEQ_LENGTH."""
    import torch
    from sentence_transformers import SentenceTransformer

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    kwargs: dict[str, Any] = {"device": device}
    if device == "cuda":
        kwargs["model_kwargs"] = {"torch_dtype": torch.float16}
    model = SentenceTransformer(model_name, **kwargs)
    model.max_seq_length = MAX_SEQ_LENGTH
    return model


def encode(model: Any, texts: Sequence[str], batch_size: int = 64) -> Matrix:
    vectors = model.encode(
        list(texts),
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return np.asarray(vectors, dtype=np.float32)


def encode_queries(model: Any, model_name: str, queries: Sequence[str]) -> Matrix:
    prefix = query_prefix(model_name)
    return encode(model, [prefix + " ".join(q.split()) for q in queries])


def model_fingerprint(model_name: str) -> str:
    """Hub models: the name. Local model dirs: name + size/mtime of every file, so a model
    retrained into the same directory never reuses stale cached embeddings."""
    path = Path(model_name)
    if not path.is_dir():
        return model_name
    stats = sorted(
        f"{p.relative_to(path).as_posix()}:{p.stat().st_size}:{p.stat().st_mtime_ns}"
        for p in path.rglob("*")
        if p.is_file()
    )
    return "\x00".join([path.resolve().as_posix(), *stats])


def encode_corpus(model: Any, model_name: str, chunks: Sequence[Chunk], cache_dir: Path) -> Matrix:
    """Corpus embeddings, cached by model fingerprint + exact passage texts."""
    passages = [c.passage for c in chunks]
    key = "\x00".join([model_fingerprint(model_name), *passages])
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "__", model_name).strip("_")
    path = cache_dir / f"{safe_name}-{digest[:16]}.npy"
    if path.exists():
        cached: Matrix = np.load(path)
        if cached.shape[0] == len(passages):
            return cached
    log.info("encoding %d passages with %s", len(passages), model_name)
    vectors = encode(model, passages)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, vectors)
    return vectors


def rank_of(scores: Matrix, positive_index: int) -> int:
    """1-based rank of ``positive_index`` in one row of scores (ties count against it)."""
    return int((scores > scores[positive_index]).sum()) + 1
