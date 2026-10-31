import tempfile
from pathlib import Path

from app.callgraph import build_edges
from app.config import MAX_REPO_KB, MAX_SYMBOLS
from app.db import get_connection
from app.embeddings import chunk_to_text, embed_documents
from app.ingest.clone import clone_repo, iter_source_files, remove_repo
from app.ingest.github import repo_size_kb
from app.parsing import parse_python


def clean(text):
    """Postgres text columns cannot store NUL characters, so remove them."""
    return text.replace("\x00", "") if text else text


def set_status(repo_id: int, status: str, error: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE repositories SET status = %s, error = %s WHERE id = %s",
            (status, error, repo_id),
        )


def do_indexing(repo_id: int) -> None:
    """Clone, parse, embed and save one repository, updating its status at each stage."""
    with get_connection() as conn:
        row = conn.execute("SELECT url, name FROM repositories WHERE id = %s", (repo_id,)).fetchone()
    if row is None:
        return  # the repository was deleted while it waited in the queue
    url, name = row
    owner, repo = name.split("/")

    size = repo_size_kb(owner, repo)
    if size is not None and size > MAX_REPO_KB:
        raise ValueError(
            f"This repository is too large for the free demo "
            f"({size // 1024} MB; the limit is {MAX_REPO_KB // 1024} MB)."
        )

    set_status(repo_id, "cloning")
    workdir = Path(tempfile.mkdtemp())
    root = workdir / repo
    files = []  # (relative path, language, full text, parsed file)
    try:
        sha = clone_repo(url, root)
        print(f"Cloned {name} at {sha[:8]}")

        set_status(repo_id, "parsing")
        for path, language in iter_source_files(root):
            if language != "python":
                continue
            rel = path.relative_to(root).as_posix()
            source = path.read_bytes()
            content = clean(source.decode("utf-8", errors="replace"))
            files.append((rel, language, content, parse_python(source, rel)))
    finally:
        remove_repo(workdir)

    entries = [(rel, s) for rel, _, _, parsed in files for s in parsed.symbols]
    if not entries:
        raise ValueError("No Python code found in this repository.")
    if len(entries) > MAX_SYMBOLS:
        raise ValueError(
            f"This repository is too large for the free demo "
            f"({len(entries)} functions and classes; the limit is {MAX_SYMBOLS})."
        )
    print(f"Parsed {len(files)} files, {len(entries)} symbols")

    set_status(repo_id, "embedding")
    print("Embedding... (this is the slow part)")
    vectors = embed_documents([chunk_to_text(s) for _, s in entries])

    set_status(repo_id, "saving")
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
                s.start_line, s.end_line, clean(s.signature),
                clean(s.docstring), clean(s.code), vec,
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