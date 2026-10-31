import sys

import numpy as np

results = []
state = {}


def run(name, func):
    try:
        detail = func()
        print(f"PASS  {name}" + (f"  ({detail})" if detail else ""))
        results.append(True)
    except Exception as error:
        print(f"FAIL  {name}  ->  {type(error).__name__}: {error}")
        results.append(False)


def check_tables():
    from app.db import get_connection

    needed = {
        "repositories", "files", "chunks", "symbol_edges", "users",
        "user_repositories", "conversations", "messages", "question_log", "answer_cache",
    }
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
    missing = needed - {row[0] for row in rows}
    if missing:
        raise RuntimeError(f"missing tables: {sorted(missing)}")
    return f"{len(needed)} tables present"


def check_repos():
    from app.db import get_connection

    with get_connection() as conn:
        rows = conn.execute(
            """SELECT r.id, r.name, (SELECT count(*) FROM chunks c WHERE c.repo_id = r.id)
               FROM repositories r WHERE r.status = 'ready' ORDER BY r.id"""
        ).fetchall()
    if not rows:
        raise RuntimeError("no repository is indexed yet")
    state["repo_id"] = rows[-1][0]
    return "; ".join(f"{name} (id {rid}, {count} symbols)" for rid, name, count in rows)


def check_embedding():
    from app.embeddings import embed_query

    vector = embed_query("how are tokens signed")
    if vector.shape != (384,):
        raise RuntimeError(f"unexpected shape {vector.shape}")
    if abs(float(np.linalg.norm(vector)) - 1.0) > 0.01:
        raise RuntimeError("the vector is not normalised")
    return "384 numbers, length 1.0"


def check_search():
    from app.search import hybrid_search

    found = hybrid_search(state["repo_id"], "how does error handling work", limit=3)
    if not found:
        raise RuntimeError("search returned nothing")
    state["symbol"] = found[0].qualified_name
    return f"top result: {found[0].qualified_name}"


def check_tools():
    from app.tools import run_tool

    code = run_tool(state["repo_id"], "read_symbol", {"symbol": state["symbol"]})
    if "No function or class" in code or code.startswith("The tool"):
        raise RuntimeError(code[:120])
    # A made-up argument must be ignored, not cause an error.
    files = run_tool(state["repo_id"], "list_files", {"prefix": "", "bogus": 1})
    if files.startswith("Bad arguments"):
        raise RuntimeError(files[:120])
    return "read_symbol and list_files work"


def check_graph():
    from app.db import get_connection

    with get_connection() as conn:
        count = conn.execute(
            "SELECT count(*) FROM symbol_edges WHERE repo_id = %s", (state["repo_id"],)
        ).fetchone()[0]
    if count == 0:
        raise RuntimeError("the call graph is empty")
    return f"{count} edges"


def check_cache_and_limits():
    from app.answer_cache import get_cached, save_answer
    from app.db import get_connection

    repo_id = state["repo_id"]
    save_answer(repo_id, "smoke test question?", "ok", ["step"], 1)
    got = get_cached(repo_id, "  Smoke test QUESTION ")
    if got is None or got["answer"] != "ok":
        raise RuntimeError("a saved answer could not be read back")
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM answer_cache WHERE repo_id = %s AND question_key = 'smoke test question'",
            (repo_id,),
        )
        conn.execute("INSERT INTO question_log (ip_hash) VALUES ('smoke-test')")
        conn.execute("DELETE FROM question_log WHERE ip_hash = 'smoke-test'")
    return "answer cache and question log work"


def check_api():
    from fastapi.testclient import TestClient

    from app.api import app

    client = TestClient(app)
    for path in ("/health", "/config", "/repos"):
        response = client.get(path)
        if response.status_code != 200:
            raise RuntimeError(f"GET {path} returned {response.status_code}")
    return "/health, /config and /repos answer"


def check_llm_settings():
    from app import config

    missing = [n for n in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL") if not getattr(config, n)]
    if missing:
        raise RuntimeError(f"not set in .env: {missing}")
    return f"model {config.LLM_MODEL}"


def check_settings():
    from app import config

    return (
        f"DEMO_MODE={config.DEMO_MODE}, {config.QUESTIONS_PER_IP_PER_HOUR} per visitor per hour, "
        f"{config.QUESTIONS_PER_DAY} per day, repo limit {config.MAX_REPO_KB // 1024} MB"
    )


if __name__ == "__main__":
    run("database tables exist", check_tables)
    run("indexed repositories", check_repos)
    if state.get("repo_id"):
        run("embeddings (ONNX)", check_embedding)
        run("search", check_search)
        if state.get("symbol"):
            run("agent tools", check_tools)
        run("call graph", check_graph)
        run("answer cache and rate-limit table", check_cache_and_limits)
    run("API answers in-process", check_api)
    run("LLM settings present (not called)", check_llm_settings)
    run("demo settings", check_settings)

    print(f"\n{sum(results)} of {len(results)} checks passed")
    sys.exit(0 if all(results) else 1)