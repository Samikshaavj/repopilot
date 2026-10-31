import threading

import psycopg

from app.db import get_connection
from app.ingest.clone import parse_github_url
from app.pipeline import do_indexing, set_status

# One repository is indexed at a time, so memory use stays predictable.
_INDEX_LOCK = threading.Lock()

IN_PROGRESS = ("pending", "cloning", "parsing", "embedding", "saving")


def create_repository(url: str, force: bool = False, allow_new: bool = True):
    """Make sure a repositories row exists. Returns (id, status, needs_indexing).

    Raises ValueError for a bad URL, and PermissionError when allow_new is False
    and the repository is not already indexed (demo mode).
    """
    clean_url, owner, repo = parse_github_url(url)
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, status FROM repositories WHERE url = %s", (clean_url,)
            ).fetchone()
            if row and not force and row[1] == "ready":
                return row[0], "ready", False
            if row and not force and row[1] in IN_PROGRESS:
                return row[0], row[1], False
            if not allow_new:
                raise PermissionError(
                    "This demo only includes the showcase repositories. Pick one from the list."
                )
            if row:  # failed, or a forced re-index: start clean
                conn.execute("DELETE FROM repositories WHERE id = %s", (row[0],))
            new_id = conn.execute(
                "INSERT INTO repositories (url, name, status) VALUES (%s, %s, 'pending') RETURNING id",
                (clean_url, f"{owner}/{repo}"),
            ).fetchone()[0]
        return new_id, "pending", True
    except psycopg.errors.UniqueViolation:
        # Someone else added the same URL a moment ago: use theirs.
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, status FROM repositories WHERE url = %s", (clean_url,)
            ).fetchone()
        return row[0], row[1], False


def run_indexing(repo_id: int) -> None:
    """Index one repository, updating its status as it goes. Never raises."""
    with _INDEX_LOCK:
        try:
            do_indexing(repo_id)
        except Exception as error:
            print(f"Indexing failed: {error}")
            set_status(repo_id, "failed", str(error)[:500])


def index_repository(url: str, force: bool = False) -> int:
    """Command-line entry point: create the row, then index it right away."""
    repo_id, status, needs_indexing = create_repository(url, force)
    if not needs_indexing:
        print(f"Nothing to do: repository {repo_id} is {status}.")
        return repo_id
    run_indexing(repo_id)
    return repo_id