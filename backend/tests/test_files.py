from fastapi.testclient import TestClient

from app import files
from app.api import app

client = TestClient(app)


class FakeConnection:
    """Stands in for the database: returns the rows we give it."""

    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        return self

    def fetchall(self):
        return self.rows


def use_rows(monkeypatch, rows):
    monkeypatch.setattr(files, "get_connection", lambda: FakeConnection(rows))


def test_window_around_the_cited_lines(monkeypatch):
    text = "\n".join(f"line {n}" for n in range(1, 101))
    use_rows(monkeypatch, [("pkg/a.py", text)])

    response = client.get("/repos/1/file", params={"path": "pkg/a.py", "start": 50, "end": 52})
    data = response.json()

    assert response.status_code == 200
    assert (data["highlight_start"], data["highlight_end"]) == (50, 52)
    assert data["first_line"] == 35
    assert data["lines"][0] == "line 35"
    assert data["lines"][-1] == "line 67"


def test_unknown_file_is_404(monkeypatch):
    use_rows(monkeypatch, [])
    response = client.get("/repos/1/file", params={"path": "nope.py", "start": 1})
    assert response.status_code == 404


def test_line_past_the_end_is_rejected(monkeypatch):
    use_rows(monkeypatch, [("a.py", "one\ntwo")])
    response = client.get("/repos/1/file", params={"path": "a.py", "start": 500})
    assert response.status_code == 400