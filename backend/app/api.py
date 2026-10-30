from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agent import ask
from app.db import get_connection
from app.indexer import create_repository, run_indexing

app = FastAPI(title="RepoPilot API")

# Lets the React dev server (a different port) call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AddRepoRequest(BaseModel):
    url: str = Field(max_length=200)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


REPO_COLUMNS = """
    r.id, r.url, r.name, r.status, r.error, r.commit_sha, r.created_at,
    (SELECT count(*) FROM files f WHERE f.repo_id = r.id),
    (SELECT count(*) FROM chunks c WHERE c.repo_id = r.id)
"""


def _repo_dict(row) -> dict:
    return {
        "id": row[0],
        "url": row[1],
        "name": row[2],
        "status": row[3],
        "error": row[4],
        "commit": row[5][:8] if row[5] else None,
        "created_at": row[6].isoformat(),
        "files": row[7],
        "symbols": row[8],
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/repos", status_code=202)
def add_repo(body: AddRepoRequest, background: BackgroundTasks):
    try:
        repo_id, status, needs_indexing = create_repository(body.url)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    if needs_indexing:
        background.add_task(run_indexing, repo_id)
    return {"id": repo_id, "status": status}


@app.get("/repos")
def list_repos():
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT {REPO_COLUMNS} FROM repositories r ORDER BY r.created_at DESC LIMIT 50"
        ).fetchall()
    return [_repo_dict(r) for r in rows]


@app.get("/repos/{repo_id}")
def get_repo(repo_id: int):
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {REPO_COLUMNS} FROM repositories r WHERE r.id = %s", (repo_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return _repo_dict(row)


@app.post("/repos/{repo_id}/ask")
def ask_repo(repo_id: int, body: AskRequest):
    with get_connection() as conn:
        row = conn.execute("SELECT status FROM repositories WHERE id = %s", (repo_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    if row[0] != "ready":
        raise HTTPException(status_code=409, detail=f"Repository is not ready (status: {row[0]})")

    try:
        result = ask(repo_id, body.question)
    except RuntimeError as error:  # for example: the free LLM quota is used up
        raise HTTPException(status_code=503, detail=str(error))

    return {
        "answer": result.answer,
        "tokens": result.tokens,
        "stopped_at_step_limit": result.hit_step_limit,
        "steps": [{"tool": s.name, "arguments": s.arguments} for s in result.steps],
    }

from app.stream import router as stream_router  # noqa: E402

app.include_router(stream_router)