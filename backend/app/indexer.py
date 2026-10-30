import tempfile
import threading
from pathlib import Path

import psycopg

from app.callgraph import build_edges
from app.db import get_connection
from app.embeddings import chunk_to_text, embed_documents
from app.ingest.clone import (
    clone_repo,
    iter_source_files,
    parse_github_url,
    remove_repo,
)
from app.parsing import parse_python

# One repository is indexed at a time, so memory use stays predictable.
_INDEX_LOCK = threading.Lock()

IN_PROGRESS = ("pending", "cloning", "parsing", "embedding", "saving")


def _clean(text):
    """Postgres text columns cannot store NUL characters, so remove them."""
    return text.replace("\x00", "") if text else text


def _set_status(repo_id: int, status: str, error: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE repositories SET status = %s, error = %s WHERE id = %s",
            (status, error, repo_id),
        )


def create_repository(url: str, force: bool = False):
    """Make sure a repositories row exists. Returns (id, status, needs_indexing)."""
    clean_url, owner, repo = parse_github_url(url)  # raises ValueError for bad URLs
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, status FROM repositories WHERE url = %s", (clean_url,)
            ).fetchone()
            if row and not force and row[1] == "ready":
                return row[0], "ready", False
            if row and not force and row[1] in IN_PROGRESS:
                return row[0], row[1], False
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
            _do_indexing(repo_id)
        except Exception as error:
            print(f"Indexing failed: {error}")
            _set_status(repo_id, "failed", str(error)[:500])


def _do_indexing(repo_id: int) -> None:
    with get_connection() as conn:
        row = conn.execute("SELECT url, name FROM repositories WHERE id = %s", (repo_id,)).fetchone()
    if row is None:
        return  # the repository was deleted while it waited in the queue
    url, name = row
    repo = name.split("/")[1]

    _set_status(repo_id, "cloning")
    workdir = Path(tempfile.mkdtemp())
    root = workdir / repo
    files = []  # (relative path, language, full text, parsed file)
    try:
        sha = clone_repo(url, root)
        print(f"Cloned {name} at {sha[:8]}")

        _set_status(repo_id, "parsing")
        for path, language in iter_source_files(root):
            if language != "python":
                continue
            rel = path.relative_to(root).as_posix()
            source = path.read_bytes()
            content = _clean(source.decode("utf-8", errors="replace"))
            files.append((rel, language, content, parse_python(source, rel)))
    finally:
        remove_repo(workdir)

    entries = [(rel, s) for rel, _, _, parsed in files for s in parsed.symbols]
    if not entries:
        raise ValueError("No Python code found in this repository.")
    print(f"Parsed {len(files)} files, {len(entries)} symbols")

    _set_status(repo_id, "embedding")
    print("Embedding... (this is the slow part)")
    vectors = embed_documents([chunk_to_text(s) for _, s in entries])

    _set_status(repo_id, "saving")
    print("Saving to database...")
    with get_connection() as conn:
        file_ids = {}
        for rel, language, content, _ in files:
            file_ids[rel] = conn.execute(
                """INSERT INTO files (repo_id, path, language, content)
                   VALUES (%s, %s, %s, %s) RETURNING id""",
                (repo_id, rel, language, content),
            ).fetchone()[0]

        rows = [
            (
                repo_id, file_ids[rel], s.kind, s.name, s.qualified_name,
                s.start_line, s.end_line, _clean(s.signature),
                _clean(s.docstring), _clean(s.code), vec,
            )
            for (rel, s), vec in zip(entries, vectors)
        ]
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO chunks
                   (repo_id, file_id, kind, name, qualified_name, start_line,
                    end_line, signature, docstring, code, embedding)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                rows,
                returning=True,
            )
            chunk_ids = []
            while True:
                chunk_ids.append(cur.fetchone()[0])
                if not cur.nextset():
                    break

            edges = build_edges(entries, chunk_ids)
            cur.executemany(
                """INSERT INTO symbol_edges
                   (repo_id, src_chunk, dst_name, dst_chunk, kind)
                   VALUES (%s, %s, %s, %s, 'calls')""",
                [(repo_id, src, edge_name, dst) for src, edge_name, dst in edges],
            )

        conn.execute(
            "UPDATE repositories SET status = 'ready', commit_sha = %s, error = NULL WHERE id = %s",
            (sha, repo_id),
        )

    resolved = sum(1 for _, _, dst in edges if dst is not None)
    print(f"Call graph: {len(edges)} edges ({resolved} resolved, {len(edges) - resolved} ambiguous)")
    print(f"Done. Repository id = {repo_id}")


def index_repository(url: str, force: bool = False) -> int:
    """Command-line entry point: create the row, then index it right away."""
    repo_id, status, needs_indexing = create_repository(url, force)
    if not needs_indexing:
        print(f"Nothing to do: repository {repo_id} is {status}.")
        return repo_id
    run_indexing(repo_id)
    return repo_id