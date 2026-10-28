import re
from dataclasses import dataclass, replace

from app.db import get_connection
from app.embeddings import embed_query

# Matches test files: tests/ folders, test_*.py, *_test.py, conftest.py
TEST_PATH_REGEX = r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$"

STOPWORDS = {
    "how", "does", "do", "is", "are", "the", "a", "an", "what", "where", "when",
    "why", "which", "of", "to", "in", "on", "for", "and", "or", "it", "this",
    "that", "with", "by", "from", "be", "can", "i", "me", "my", "was", "were",
}


@dataclass
class SearchResult:
    chunk_id: int
    kind: str
    qualified_name: str
    path: str
    start_line: int
    end_line: int
    docstring: str | None
    code: str
    score: float


def vector_search(
    repo_id: int, question: str, limit: int = 5, include_tests: bool = False
) -> list[SearchResult]:
    """Find the chunks whose meaning is closest to the question."""
    query_vector = embed_query(question)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.kind, c.qualified_name, f.path,
                   c.start_line, c.end_line, c.docstring, c.code,
                   1 - (c.embedding <=> %s) AS score
            FROM chunks c
            JOIN files f ON f.id = c.file_id
            WHERE c.repo_id = %s
              AND (%s OR f.path !~* %s)
            ORDER BY c.embedding <=> %s
            LIMIT %s
            """,
            (query_vector, repo_id, include_tests, TEST_PATH_REGEX, query_vector, limit),
        ).fetchall()

    return [SearchResult(*row) for row in rows]


def _to_tsquery(question: str) -> str | None:
    """Turn a question into 'word1 | word2 | word3' (match ANY important word)."""
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", question.lower())
    words = [w for w in dict.fromkeys(words) if w not in STOPWORDS and len(w) > 1]
    return " | ".join(words) if words else None


def keyword_search(
    repo_id: int, question: str, limit: int = 5, include_tests: bool = False
) -> list[SearchResult]:
    """Find chunks that contain the important words from the question."""
    tsquery = _to_tsquery(question)
    if tsquery is None:
        return []

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.kind, c.qualified_name, f.path,
                   c.start_line, c.end_line, c.docstring, c.code,
                   ts_rank(c.tsv, to_tsquery('simple', %s)) AS score
            FROM chunks c
            JOIN files f ON f.id = c.file_id
            WHERE c.repo_id = %s
              AND c.tsv @@ to_tsquery('simple', %s)
              AND (%s OR f.path !~* %s)
            ORDER BY score DESC
            LIMIT %s
            """,
            (tsquery, repo_id, tsquery, include_tests, TEST_PATH_REGEX, limit),
        ).fetchall()

    return [SearchResult(*row) for row in rows]
RRF_K = 60  # standard constant; higher = ranks matter less


def name_search(
    repo_id: int, question: str, limit: int = 5, include_tests: bool = False
) -> list[SearchResult]:
    """Find chunks whose NAME exactly equals a word in the question."""
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", question.lower())
    words = [w for w in dict.fromkeys(words) if w not in STOPWORDS and len(w) > 1]
    if not words:
        return []

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.kind, c.qualified_name, f.path,
                   c.start_line, c.end_line, c.docstring, c.code,
                   1.0 AS score
            FROM chunks c
            JOIN files f ON f.id = c.file_id
            WHERE c.repo_id = %s
              AND lower(c.name) = ANY(%s)
              AND (%s OR f.path !~* %s)
            ORDER BY (c.kind = 'class') DESC, c.qualified_name
            LIMIT %s
            """,
            (repo_id, words, include_tests, TEST_PATH_REGEX, limit),
        ).fetchall()

    return [SearchResult(*row) for row in rows]


DEFAULT_WEIGHTS = {"vector": 1.0, "keyword": 0.0, "name": 1.0}

SEARCHERS = {
    "vector": vector_search,
    "keyword": keyword_search,
    "name": name_search,
}


def hybrid_search(
    repo_id: int,
    question: str,
    limit: int = 5,
    include_tests: bool = False,
    pool: int = 20,
    weights: dict | None = None,
) -> list[SearchResult]:
    """Weighted reciprocal rank fusion. A weight of 0 skips that search entirely."""
    weights = weights or DEFAULT_WEIGHTS

    fused: dict[int, float] = {}
    first_seen: dict[int, SearchResult] = {}
    for source, searcher in SEARCHERS.items():
        weight = weights.get(source, 0.0)
        if weight == 0:
            continue
        results = searcher(repo_id, question, pool, include_tests)
        for rank, result in enumerate(results, start=1):
            fused[result.chunk_id] = fused.get(result.chunk_id, 0.0) + weight / (RRF_K + rank)
            first_seen.setdefault(result.chunk_id, result)

    best_ids = sorted(fused, key=fused.get, reverse=True)[:limit]
    return [replace(first_seen[cid], score=fused[cid]) for cid in best_ids]