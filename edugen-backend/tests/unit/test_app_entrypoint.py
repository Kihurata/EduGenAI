"""App entrypoint: health check, CORS and security headers need no database or login."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_cors_allows_frontend_dev_origin():
    resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_exposes_download_filename():
    resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert "content-disposition" in resp.headers["access-control-expose-headers"].lower()


def test_cors_ignores_unknown_origin():
    resp = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in resp.headers
