from dataclasses import dataclass

from app.db import get_connection

MAX_DEPTH = 4

# Files that are tests (same pattern as in search.py)
TEST_PATH_REGEX = r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$"


@dataclass
class GraphNode:
    chunk_id: int
    qualified_name: str
    kind: str
    path: str
    start_line: int
    end_line: int
    depth: int  # 0 = the starting symbol, 1 = direct neighbour, 2 = neighbour of a neighbour...


def find_symbols(repo_id: int, name: str) -> list[GraphNode]:
    """Find chunks by exact qualified name (Signer.sign) or plain name (sign)."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.qualified_name, c.kind, f.path, c.start_line, c.end_line
            FROM chunks c
            JOIN files f ON f.id = c.file_id
            WHERE c.repo_id = %s AND (c.qualified_name = %s OR c.name = %s)
            ORDER BY (c.qualified_name = %s) DESC, f.path, c.start_line
            """,
            (repo_id, name, name, name),
        ).fetchall()
    return [GraphNode(*row, depth=0) for row in rows]


def _expand(conn, repo_id, frontier, direction, include_tests):
    """One step along the graph from every chunk in `frontier`."""
    # Column names cannot be passed as %s parameters, so we pick them from this
    # fixed pair. They never come from user input.
    near, far = ("src_chunk", "dst_chunk") if direction == "callees" else ("dst_chunk", "src_chunk")
    return conn.execute(
        f"""
        SELECT DISTINCT n.id, n.qualified_name, n.kind, f.path, n.start_line, n.end_line
        FROM symbol_edges e
        JOIN chunks n ON n.id = e.{far}
        JOIN files f ON f.id = n.file_id
        WHERE e.repo_id = %s
          AND e.{near} = ANY(%s)
          AND (%s OR f.path !~* %s)
        """,
        (repo_id, list(frontier), include_tests, TEST_PATH_REGEX),
    ).fetchall()


def _walk_graph(repo_id, chunk_id, direction, depth, include_tests):
    depth = max(1, min(depth, MAX_DEPTH))
    seen = {chunk_id}      # chunks already visited (stops infinite loops)
    frontier = {chunk_id}  # the chunks we expand in this round
    found: list[GraphNode] = []

    with get_connection() as conn:
        for level in range(1, depth + 1):
            if not frontier:
                break
            rows = _expand(conn, repo_id, frontier, direction, include_tests)
            frontier = set()
            for row in rows:
                if row[0] in seen:
                    continue
                seen.add(row[0])
                frontier.add(row[0])
                found.append(GraphNode(*row, depth=level))

    return sorted(found, key=lambda n: (n.depth, n.path, n.start_line))


def get_callees(repo_id: int, chunk_id: int, depth: int = 1, include_tests: bool = False):
    """What does this function call? (and what do those call, up to `depth` levels)"""
    return _walk_graph(repo_id, chunk_id, "callees", depth, include_tests)


def get_callers(repo_id: int, chunk_id: int, depth: int = 1, include_tests: bool = False):
    """Who calls this function? (and who calls those, up to `depth` levels)"""
    return _walk_graph(repo_id, chunk_id, "callers", depth, include_tests)


def unresolved_calls(repo_id: int, chunk_id: int) -> dict[str, list[str]]:
    """Calls we could not pin to one function, with every possible candidate."""
    with get_connection() as conn:
        names = [
            r[0]
            for r in conn.execute(
                """SELECT DISTINCT dst_name FROM symbol_edges
                   WHERE src_chunk = %s AND dst_chunk IS NULL ORDER BY dst_name""",
                (chunk_id,),
            ).fetchall()
        ]
        result = {}
        for name in names:
            rows = conn.execute(
                """SELECT c.qualified_name FROM chunks c
                   JOIN files f ON f.id = c.file_id
                   WHERE c.repo_id = %s AND c.name = %s AND f.path !~* %s
                   ORDER BY 1""",
                (repo_id, name, TEST_PATH_REGEX),
            ).fetchall()
            result[name] = [r[0] for r in rows]
    return result