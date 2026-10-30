import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import stream
from app.api import app as fastapi_app

client = TestClient(fastapi_app)


def read_events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def test_stream_sends_start_then_steps_then_answer(monkeypatch):
    def fake_ask(repo_id, question, on_step=None):
        on_step(SimpleNamespace(name="search_code", arguments={"query": "max_age"}, result="..."))
        return SimpleNamespace(answer="It checks max_age.", tokens=123, hit_step_limit=False, steps=[1])

    monkeypatch.setattr(stream, "ask", fake_ask)
    monkeypatch.setattr(stream, "repo_status", lambda repo_id: "ready")

    response = client.post("/repos/1/ask/stream", json={"question": "How does max_age work?"})
    events = read_events(response)

    assert response.status_code == 200
    assert [e["type"] for e in events] == ["start", "step", "answer"]
    assert events[1]["label"].startswith("Searching")
    assert events[2]["answer"] == "It checks max_age."


def test_stream_reports_agent_errors_as_events(monkeypatch):
    def failing_ask(repo_id, question, on_step=None):
        raise RuntimeError("Still rate limited after several retries.")

    monkeypatch.setattr(stream, "ask", failing_ask)
    monkeypatch.setattr(stream, "repo_status", lambda repo_id: "ready")

    response = client.post("/repos/1/ask/stream", json={"question": "Anything at all?"})
    events = read_events(response)

    assert events[-1]["type"] == "error"
    assert "rate limited" in events[-1]["message"]


def test_stream_refuses_repositories_that_are_not_ready(monkeypatch):
    monkeypatch.setattr(stream, "repo_status", lambda repo_id: "embedding")
    response = client.post("/repos/1/ask/stream", json={"question": "Anything at all?"})
    assert response.status_code == 409


def test_stream_unknown_repository_is_404(monkeypatch):
    monkeypatch.setattr(stream, "repo_status", lambda repo_id: None)
    response = client.post("/repos/999/ask/stream", json={"question": "Anything at all?"})
    assert response.status_code == 404