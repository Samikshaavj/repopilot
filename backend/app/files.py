from fastapi import APIRouter, HTTPException, Query

from app.db import get_connection

router = APIRouter()

CONTEXT_LINES = 15  # lines shown before and after the cited range
MAX_WINDOW = 400    # never send more than this many lines


@router.get("/repos/{repo_id}/file")
def read_file_window(
    repo_id: int,
    path: str = Query(..., max_length=300),
    start: int = Query(1, ge=1),
    end: int | None = Query(None, ge=1),
):
    """Return a window of lines from a file of this repository, around start-end."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT path, content FROM files
               WHERE repo_id = %s
                 AND (path = %s OR right(path, length(%s::text) + 1) = '/' || %s::text)
               ORDER BY (path = %s) DESC
               LIMIT 2""",
            (repo_id, path, path, path, path),
        ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="File not found in this repository")
    if len(rows) > 1 and rows[0][0] != path:
        raise HTTPException(status_code=409, detail="Several files match that path")

    real_path, content = rows[0]
    lines = content.splitlines()
    total = len(lines)
    if start > total:
        raise HTTPException(
            status_code=400, detail=f"Line {start} is past the end of the file ({total} lines)"
        )

    end = min(max(end or start, start), total)
    first = max(1, start - CONTEXT_LINES)
    last = min(total, end + CONTEXT_LINES, first + MAX_WINDOW - 1)

    return {
        "path": real_path,
        "total_lines": total,
        "first_line": first,
        "highlight_start": start,
        "highlight_end": end,
        "lines": lines[first - 1 : last],
    }