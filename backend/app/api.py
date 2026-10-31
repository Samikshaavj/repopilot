from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.config import CORS_ORIGINS, DEMO_MODE
from app.db import get_connection
from app.files import router as files_router
from app.indexer import create_repository, run_indexing
from app.stream import router as stream_router

app = FastAPI(title="RepoPilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(stream_router)
app.include_router(files_router)


class AddRepoRequest(BaseModel):
    url: str = Field(max_length=200)


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


@app.get("/", include_in_schema=False)
def root():
    return {"name": "RepoPilot API", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def config():
    """Settings the frontend needs to know about."""
    return {"demo_mode": DEMO_MODE}


@app.post("/repos", status_code=202)
def add_repo(body: AddRepoRequest, background: BackgroundTasks):
    try:
        repo_id, status, needs_indexing = create_repository(body.url, allow_new=not DEMO_MODE)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    if needs_indexing:
        background.add_task(run_indexing, repo_id)
    return {"id": repo_id, "status": status}


@app.get("/repos")
def list_repos():
    where = "WHERE r.status = 'ready'" if DEMO_MODE else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT {REPO_COLUMNS} FROM repositories r {where} ORDER BY r.created_at DESC LIMIT 50"
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