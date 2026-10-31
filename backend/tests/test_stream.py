import json
import threading
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import stream
from app.api import app as fastapi_app

client = TestClient(fastapi_app)


def read_events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def prepare(monkeypatch, cached=None, saved=None, allowed=True):
    """Replace everything that touches the database or the LLM with simple fakes."""
    monkeypatch.setattr(stream, "repo_status", lambda repo_id: "ready")
    monkeypatch.setattr(stream, "get_cached", lambda repo_id, question: cached)

    def fake_save(*args):
        if saved is not None:
            saved.append(args)

    monkeypatch.setattr(stream, "save_answer", fake_save)

    def fake_limit(request):
        if not allowed:
            raise HTTPException(status_code=429, detail="slow down")

    monkeypatch.setattr(stream, "check_question_allowed", fake_limit)


def fake_agent(answer="It checks max_age.", limited=False):
    def fake_ask(repo_id, question, on_step=None):
        on_step(SimpleNamespace(name="search_code", arguments={"query": "max_age"}, result="..."))
        return SimpleNamespace(answer=answer, tokens=123, hit_step_limit=limited, steps=[1])

    return fake_ask


def ask(question="How does max_age work?"):
    return client.post("/repos/1/ask/stream", json={"question": question})


def test_stream_sends_start_then_steps_then_answer_and_saves_it(monkeypatch):
    saved = []
    prepare(monkeypatch, saved=saved)
    monkeypatch.setattr(stream, "ask", fake_agent())

    response = ask()
    events = read_events(response)

    assert response.status_code == 200
    assert [e["type"] for e in events] == ["start", "step", "answer"]
    assert events[1]["label"].startswith("Searching")
    assert events[2]["answer"] == "It checks max_age."
    assert events[2]["cached"] is False
    assert len(saved) == 1


def test_answers_that_ran_out_of_steps_are_not_saved(monkeypatch):
    saved = []
    prepare(monkeypatch, saved=saved)
    monkeypatch.setattr(stream, "ask", fake_agent(limited=True))

    events = read_events(ask())

    assert events[-1]["type"] == "answer"
    assert saved == []


def test_saved_answer_is_replayed_without_calling_the_agent(monkeypatch):
    cached = {"answer": "Saved answer.", "steps": ["Searching the code for “max_age”"], "tokens": 99}
    prepare(monkeypatch, cached=cached)

    def must_not_run(*args, **kwargs):
        raise AssertionError("the agent must not run for a saved answer")

    monkeypatch.setattr(stream, "ask", must_not_run)

    events = read_events(ask())

    assert [e["type"] for e in events] == ["start", "step", "answer"]
    assert events[-1]["cached"] is True
    assert events[-1]["answer"] == "Saved answer."


def test_saved_answers_are_not_rate_limited(monkeypatch):
    cached = {"answer": "Saved answer.", "steps": [], "tokens": 0}
    prepare(monkeypatch, cached=cached, allowed=False)
    assert ask().status_code == 200


def test_new_questions_are_rate_limited(monkeypatch):
    prepare(monkeypatch, allowed=False)
    monkeypatch.setattr(stream, "ask", fake_agent())
    assert ask().status_code == 429


def test_busy_server_says_try_again(monkeypatch):
    prepare(monkeypatch)
    busy = threading.BoundedSemaphore(1)
    busy.acquire()  # the only place is taken
    monkeypatch.setattr(stream, "SLOTS", busy)
    assert ask().status_code == 429


def test_stream_reports_agent_errors_as_events(monkeypatch):
    prepare(monkeypatch)

    def failing_ask(repo_id, question, on_step=None):
        raise RuntimeError("Still rate limited after several retries.")

    monkeypatch.setattr(stream, "ask", failing_ask)

    events = read_events(ask())

    assert events[-1]["type"] == "error"
    assert "rate limited" in events[-1]["message"]


def test_stream_refuses_repositories_that_are_not_ready(monkeypatch):
    monkeypatch.setattr(stream, "repo_status", lambda repo_id: "embedding")
    assert ask().status_code == 409


def test_stream_unknown_repository_is_404(monkeypatch):
    monkeypatch.setattr(stream, "repo_status", lambda repo_id: None)
    assert ask().status_code == 404