"""Local embedding model + cosine similarity for recipe semantic search.

Everything here runs inside dbmcp with no network dependency at request time: the model
is a small local ONNX model (`fastembed`), pre-warmed into the Docker image at build time
(see Dockerfile, which also sets FASTEMBED_CACHE_PATH to the same image-local directory
the pre-warm step used - not the /data volume, which is a host bind mount at runtime and
would shadow anything baked there during the build). One embedding per recipe, built
from its whole text - no chunking, no separate vector-database engine. At catalog scale
(tens-hundreds of rows) a full re-scan with numpy cosine similarity per search is
simple, always consistent with the `recipes` table (no cache to invalidate), and fast
enough.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np

_MODEL_NAME = "BAAI/bge-small-en-v1.5"
# Outside Docker (e.g. `python init_db.py` for local dev) there is no /opt volume, so
# default next to the package - same convention as config.py's _DEFAULT_DB_PATH.
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / "fastembed_cache"
_model: Any = None


def _get_model() -> Any:
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        cache_dir = os.environ.get("FASTEMBED_CACHE_PATH", str(_DEFAULT_CACHE_DIR))
        _model = TextEmbedding(model_name=_MODEL_NAME, cache_dir=cache_dir)
    return _model


def embed_text(text: str) -> list[float]:
    """Embed one piece of text into a fixed-length vector."""
    (vector,) = _get_model().embed([text])
    return vector.tolist()


def embedding_text_for(recipe: dict[str, Any]) -> str:
    """Build the single string a recipe's embedding is computed from (no chunking)."""
    ingredient_names = ", ".join(str(item.get("item_name", "")) for item in recipe.get("ingredients", []))
    parts = [
        str(recipe.get("name", "")),
        str(recipe.get("origin", "")),
        ingredient_names,
        " ".join(recipe.get("instructions", [])),
        ", ".join(recipe.get("tags", [])),
        ", ".join(recipe.get("meal_types", [])),
        str(recipe.get("source", "")),
    ]
    return "\n".join(part for part in parts if part.strip())


def cosine_top_k(query_vector: list[float], candidates: list[tuple[int, list[float]]], k: int) -> list[tuple[int, float]]:
    """Rank `candidates` (id, vector) by cosine similarity to `query_vector`, best first."""
    if not candidates:
        return []
    ids = [candidate_id for candidate_id, _ in candidates]
    matrix = np.array([vector for _, vector in candidates], dtype=float)
    query = np.array(query_vector, dtype=float)
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query)
    similarities = np.divide(matrix @ query, norms, out=np.zeros(len(candidates)), where=norms > 0)
    order = np.argsort(-similarities)[: max(k, 0)]
    return [(ids[i], float(similarities[i])) for i in order]
