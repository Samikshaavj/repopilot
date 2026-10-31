from pathlib import Path

import numpy as np

MODEL_NAME = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# The model files live inside the project, so a server can download them once, at build time.
CACHE_DIR = Path(__file__).resolve().parent.parent / "models_cache"

_model = None


def get_model():
    """Load the model once and reuse it (loading takes a few seconds)."""
    global _model
    if _model is None:
        # Imported here, so the API and the tests start fast when they never embed anything.
        from fastembed import TextEmbedding

        _model = TextEmbedding(model_name=MODEL_NAME, cache_dir=str(CACHE_DIR))
    return _model


def _normalize(vectors) -> np.ndarray:
    """Scale every vector to length 1, so dot product equals cosine similarity."""
    array = np.asarray(list(vectors), dtype=np.float32)
    return array / np.linalg.norm(array, axis=1, keepdims=True)


def chunk_to_text(symbol) -> str:
    """The text we embed for one symbol: a short header, docstring, then code."""
    parts = [f"{symbol.kind} {symbol.qualified_name} in {symbol.file_path}"]
    if symbol.docstring:
        parts.append(symbol.docstring)
    parts.append(symbol.code)
    return "\n".join(parts)


def embed_documents(texts: list[str], batch_size: int = 32):
    """Embed code chunks (no prefix, as the model expects for documents)."""
    return _normalize(get_model().embed(texts, batch_size=batch_size))


def embed_query(text: str):
    """Embed a user's question (with the prefix the model expects for queries)."""
    return _normalize(get_model().embed([QUERY_PREFIX + text]))[0]