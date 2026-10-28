import logging

from app.db import get_connection
from app.graph import find_symbols, get_callees, get_callers, unresolved_calls
from app.search import hybrid_search

logger = logging.getLogger(__name__)

MAX_RESULT_CHARS = 6000   # no tool result may be longer than this
MAX_FILE_LINES = 150      # read_file returns at most this many lines per call
SNIPPET_CHARS = 700       # how much code search_code shows per result


def _truncate(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... [output truncated; ask for something narrower]"


def tool_search_code(repo_id: int, query: str, limit: int = 5) -> str:
    limit = max(1, min(int(limit), 8))
    results = hybrid_search(repo_id, query, limit=limit)
    if not results:
        return "No results. Try different words, or an exact function or class name."
    parts = []
    for i, r in enumerate(results, start=1):
        code = r.code if len(r.code) <= SNIPPET_CHARS else r.code[:SNIPPET_CHARS] + "\n    ..."
        parts.append(
            f"[{i}] {r.kind} {r.qualified_name}  ({r.path}:{r.start_line}-{r.end_line})\n{code}"
        )
    return _truncate("\n\n".join(parts))


def tool_read_file(repo_id: int, path: str, start_line: int = 1, end_line: int | None = None) -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT content FROM files WHERE repo_id = %s AND path = %s",
            (repo_id, path),
        ).fetchone()
    if row is None:
        return f"No file named {path!r}. Use list_files to see the exact paths."

    lines = row[0].splitlines()
    start = max(1, int(start_line or 1))
    if start > len(lines):
        return f"{path} has only {len(lines)} lines."
    end = int(end_line) if end_line else start + MAX_FILE_LINES - 1
    end = min(end, start + MAX_FILE_LINES - 1, len(lines))

    numbered = [f"{n:>5}  {lines[n - 1]}" for n in range(start, end + 1)]
    header = f"{path}, lines {start}-{end} of {len(lines)}"
    return _truncate(header + "\n" + "\n".join(numbered))


def tool_list_files(repo_id: int, prefix: str = "") -> str:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT path FROM files
               WHERE repo_id = %s AND starts_with(path, %s)
               ORDER BY path LIMIT 200""",
            (repo_id, prefix or ""),
        ).fetchall()
    if not rows:
        return f"No files start with {prefix!r}."
    return _truncate("\n".join(r[0] for r in rows))


def _resolve_symbol(repo_id: int, symbol: str):
    """Turn a name from the agent into one chunk. Returns (node or None, note)."""
    matches = find_symbols(repo_id, symbol)
    if not matches:
        return None, f"No function or class named {symbol!r}. Use search_code to find the exact name."
    note = ""
    if len(matches) > 1 and matches[0].qualified_name != symbol:
        names = ", ".join(m.qualified_name for m in matches[:5])
        note = (
            f"(Several symbols match: {names}. Using {matches[0].qualified_name}. "
            f"Pass the full name, like 'Class.method', to choose another.)\n"
        )
    return matches[0], note


def _format_nodes(nodes) -> str:
    if not nodes:
        return "  (none found)"
    return "\n".join(
        f"{'  ' * (n.depth - 1)}- {n.qualified_name}  ({n.path}:{n.start_line}-{n.end_line})"
        for n in nodes
    )


def tool_get_callers(repo_id: int, symbol: str, depth: int = 1) -> str:
    target, note = _resolve_symbol(repo_id, symbol)
    if target is None:
        return note
    nodes = get_callers(repo_id, target.chunk_id, int(depth))
    return _truncate(
        f"{note}Functions that call {target.qualified_name}:\n{_format_nodes(nodes)}\n"
        "(Static analysis: calls made through objects of unknown type may be missing.)"
    )


def tool_get_callees(repo_id: int, symbol: str, depth: int = 1) -> str:
    target, note = _resolve_symbol(repo_id, symbol)
    if target is None:
        return note
    nodes = get_callees(repo_id, target.chunk_id, int(depth))
    text = f"{note}Functions called by {target.qualified_name}:\n{_format_nodes(nodes)}"
    ambiguous = unresolved_calls(repo_id, target.chunk_id)
    if ambiguous:
        text += "\n\nAmbiguous calls (could not tell which function is meant):"
        for call, candidates in ambiguous.items():
            text += f"\n  {call}() could be: {', '.join(candidates) or 'unknown'}"
    return _truncate(text)


TOOL_FUNCTIONS = {
    "search_code": tool_search_code,
    "read_file": tool_read_file,
    "list_files": tool_list_files,
    "get_callers": tool_get_callers,
    "get_callees": tool_get_callees,
}

# What the model sees: the name, a description and the inputs of each tool.
TOOL_SCHEMAS = [
    {
        "name": "search_code",
        "description": (
            "Search the repository's code by meaning or by an exact function/class name. "
            "Returns the best-matching functions, classes and methods with their file path, "
            "line numbers and code. Use this first to find where something is implemented. "
            "Test files are excluded. If results look wrong, rephrase the query and try again."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for, in plain words or an exact name."},
                "limit": {"type": "integer", "description": "How many results (1-8). Default 5."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read lines from a source file, shown with line numbers. Use it after search_code "
            "to see surrounding code such as imports, constants and neighbouring functions. "
            "Returns at most 150 lines per call; pass start_line and end_line for other parts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Exact file path, e.g. src/pkg/module.py"},
                "start_line": {"type": "integer", "description": "First line to read. Default 1."},
                "end_line": {"type": "integer", "description": "Last line to read."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": (
            "List the source files in the repository, optionally only those whose path starts "
            "with a prefix such as 'src/'. Use it to understand the layout of the project."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"prefix": {"type": "string", "description": "Path prefix to filter by."}},
        },
    },
    {
        "name": "get_callers",
        "description": (
            "Find which functions call a given function or method. Use it to see where "
            "something is used. depth=2 also shows the callers of the callers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Function name, ideally 'Class.method'."},
                "depth": {"type": "integer", "description": "How many levels to follow (1-4). Default 1."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_callees",
        "description": (
            "Find which functions a given function or method calls. Use it to understand what "
            "a function depends on and how a request flows through the code. Also lists "
            "ambiguous calls the analysis could not pin to a single function."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Function name, ideally 'Class.method'."},
                "depth": {"type": "integer", "description": "How many levels to follow (1-4). Default 1."},
            },
            "required": ["symbol"],
        },
    },
]


def run_tool(repo_id: int, name: str, arguments: dict) -> str:
    """Run one tool. Errors are returned as text so the model can recover from them."""
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return f"Unknown tool {name!r}. Available tools: {', '.join(TOOL_FUNCTIONS)}."
    try:
        return func(repo_id, **arguments)
    except TypeError as error:
        return f"Bad arguments for {name}: {error}"
    except Exception as error:
        logger.exception("Tool %s failed", name)
        return f"The tool {name} failed: {error}"