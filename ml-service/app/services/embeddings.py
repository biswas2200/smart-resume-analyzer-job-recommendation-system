"""Thin wrapper around sentence-transformers. Deterministic given a fixed
model: same input always produces the same vector, no LLM call involved.
"""

from functools import lru_cache

import numpy as np

from app.config import get_settings


@lru_cache
def _get_model():
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    # revision= loads exactly the commit engine_fingerprint() hashes
    # (fingerprint.py), the same way local_ner_parser.py loads the NER model.
    return SentenceTransformer(settings.embedding_model, revision=settings.embedding_model_revision)


def embed(texts: list[str]) -> np.ndarray:
    """Embed a list of strings, returning an (n, dim) array."""
    if not texts:
        return np.empty((0, 0))
    return np.asarray(_get_model().encode(texts, normalize_embeddings=True))


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D vectors already L2-normalized by
    embed(); falls back to explicit normalization if not.
    """
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)
