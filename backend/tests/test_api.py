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