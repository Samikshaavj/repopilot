MODEL_NAME = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_model = None


def get_model():
    """Load the model once and reuse it (loading takes a few seconds)."""
    global _model
    if _model is None:
        # Imported here, not at the top of the file: importing PyTorch takes many
        # seconds, and parts of the app (the API starting up, tests) never need it.
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def chunk_to_text(symbol) -> str:
    """The text we embed for one symbol: a short header, docstring, then code."""
    parts = [f"{symbol.kind} {symbol.qualified_name} in {symbol.file_path}"]
    if symbol.docstring:
        parts.append(symbol.docstring)
    parts.append(symbol.code)
    return "\n".join(parts)


def embed_documents(texts: list[str], batch_size: int = 32):
    """Embed code chunks (no prefix, as the model expects for documents)."""
    return get_model().encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=len(texts) > 100,
    )


def embed_query(text: str):
    """Embed a user's question (with the prefix the model expects for queries)."""
    return get_model().encode(QUERY_PREFIX + text, normalize_embeddings=True)