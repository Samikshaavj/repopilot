from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_bad_url_is_rejected():
    response = client.post("/repos", json={"url": "https://example.com/not-github"})
    assert response.status_code == 400




from app import api  # noqa: E402


def test_demo_mode_refuses_new_repositories(monkeypatch):
    def refuse(url, allow_new=True):
        raise PermissionError("This demo only includes the showcase repositories.")

    monkeypatch.setattr(api, "create_repository", refuse)
    response = client.post("/repos", json={"url": "https://github.com/pallets/click"})
    assert response.status_code == 403