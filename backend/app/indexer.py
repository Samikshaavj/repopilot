import tempfile
from pathlib import Path

from app.db import get_connection
from app.embeddings import chunk_to_text, embed_documents
from app.ingest.clone import (
    clone_repo,
    iter_source_files,
    parse_github_url,
    remove_repo,
)
from app.parsing import parse_python


def _clean(text):
    """Postgres text columns cannot store NUL characters, so remove them."""
    return text.replace("\x00", "") if text else text


def index_repository(url: str) -> int:
    """Clone, parse, embed and save a repo. Returns its id in the database."""
    clean_url, owner, repo = parse_github_url(url)

    # 1. Already indexed? Then there is nothing to do.
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM repositories WHERE url = %s AND status = 'ready'",
            (clean_url,),
        ).fetchone()
    if row:
        print("Already indexed.")
        return row[0]

    # 2. Clone and parse (no database needed for this part)
    workdir = Path(tempfile.mkdtemp())
    root = workdir / repo
    files = []  # (relative path, language, full text, parsed file)
    try:
        sha = clone_repo(clean_url, root)
        print(f"Cloned {owner}/{repo} at {sha[:8]}")

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

    # 3. Embed every symbol
    print("Embedding... (this is the slow part)")
    vectors = embed_documents([chunk_to_text(s) for _, s in entries])

    # 4. Save everything in ONE transaction: all of it, or none of it
    print("Saving to database...")
    with get_connection() as conn:
        conn.execute("DELETE FROM repositories WHERE url = %s", (clean_url,))
        repo_id = conn.execute(
            """INSERT INTO repositories (url, name, commit_sha, status)
               VALUES (%s, %s, %s, 'ready') RETURNING id""",
            (clean_url, f"{owner}/{repo}", sha),
        ).fetchone()[0]

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
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                rows,
            )

    print(f"Done. Repository id = {repo_id}")
    return repo_id