"""Sentence embeddings shared by corpus indexing and query-time retrieval.

multilingual-e5 expects "passage: " / "query: " prefixes; callers pick the role and never
add the prefix themselves.
"""

from __future__ import annotations

from functools import cache
from threading import Lock

MODEL_NAME = "intfloat/multilingual-e5-small"
DIM = 384
_encode_lock = Lock()


def _device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@cache
def _model():
    from sentence_transformers import SentenceTransformer

    device = _device()
    try:
        model = SentenceTransformer(MODEL_NAME, device=device, local_files_only=True)
    except OSError:
        model = SentenceTransformer(MODEL_NAME, device=device)
    model.max_seq_length = 512
    return model


def embed_passages(texts: list[str], batch_size: int = 128) -> list[list[float]]:
    with _encode_lock:
        vectors = _model().encode([f"passage: {t}" for t in texts], batch_size=batch_size,
                                  normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    with _encode_lock:
        return _model().encode(f"query: {text}", normalize_embeddings=True).tolist()
