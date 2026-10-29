"""Sentence embeddings shared by corpus indexing and query-time retrieval.

multilingual-e5 expects "passage: " / "query: " prefixes; callers pick the role and never
add the prefix themselves.
"""

from __future__ import annotations

from functools import cache

MODEL_NAME = "intfloat/multilingual-e5-small"
DIM = 384


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

    model = SentenceTransformer(MODEL_NAME, device=_device())
    model.max_seq_length = 512
    return model


def embed_passages(texts: list[str], batch_size: int = 128) -> list[list[float]]:
    vectors = _model().encode([f"passage: {t}" for t in texts], batch_size=batch_size,
                              normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    return _model().encode(f"query: {text}", normalize_embeddings=True).tolist()
