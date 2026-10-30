import json
import logging
import queue
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent import ask
from app.db import get_connection

logger = logging.getLogger(__name__)
router = APIRouter()

HEARTBEAT_SECONDS = 15  # send a tiny "still here" message when nothing else is happening


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


def describe_step(name: str, args: dict) -> str:
    """A short human-readable label for one tool call."""
    if name == "search_code":
        return f"Searching the code for “{args.get('query', '')}”"
    if name == "read_symbol":
        return f"Reading {args.get('symbol', 'a function')}"
    if name == "read_file":
        return f"Reading {args.get('path', 'a file')}"
    if name == "list_files":
        return "Looking at the project layout"
    if name == "get_callers":
        return f"Finding what calls {args.get('symbol', 'a function')}"
    if name == "get_callees":
        return f"Finding what {args.get('symbol', 'a function')} calls"
    return f"Using {name}"


def sse(event: dict) -> str:
    """Format one event the way the SSE protocol expects: 'data: <json>' and a blank line."""
    return f"data: {json.dumps(event)}\n\n"


def repo_status(repo_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT status FROM repositories WHERE id = %s", (repo_id,)).fetchone()
    return row[0] if row else None


@router.post("/repos/{repo_id}/ask/stream")
def ask_stream(repo_id: int, body: AskRequest):
    # Check these first, so problems come back as normal HTTP errors, not as a stream.
    status = repo_status(repo_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    if status != "ready":
        raise HTTPException(status_code=409, detail=f"Repository is not ready (status: {status})")

    events: queue.Queue = queue.Queue()
    done = object()  # a unique marker meaning "no more events"

    def on_step(step) -> None:
        events.put({
            "type": "step",
            "tool": step.name,
            "arguments": step.arguments,
            "label": describe_step(step.name, step.arguments),
        })

    def worker() -> None:
        try:
            result = ask(repo_id, body.question, on_step=on_step)
            events.put({
                "type": "answer",
                "answer": result.answer,
                "tokens": result.tokens,
                "steps": len(result.steps),
                "stopped_at_step_limit": result.hit_step_limit,
            })
        except RuntimeError as error:  # for example: the free LLM quota is used up
            events.put({"type": "error", "message": str(error)})
        except Exception:
            logger.exception("The agent failed")
            events.put({"type": "error", "message": "Something went wrong while answering. Please try again."})
        finally:
            events.put(done)

    threading.Thread(target=worker, daemon=True).start()

    def generate():
        yield sse({"type": "start"})
        while True:
            try:
                item = events.get(timeout=HEARTBEAT_SECONDS)
            except queue.Empty:
                yield ": ping\n\n"  # a comment line: keeps the connection alive, ignored by clients
                continue
            if item is done:
                break
            yield sse(item)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )