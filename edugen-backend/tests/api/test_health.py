"""Kiểm tra sức khỏe dịch vụ: không cần đăng nhập."""


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def preflight(client, origin: str):
    return client.options(
        "/api/v1/exams",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


def test_cors_allows_frontend_dev_origin(client):
    resp = preflight(client, "http://localhost:5173")
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "authorization" in resp.headers["access-control-allow-headers"].lower()


def test_cors_exposes_download_filename(client):
    resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert "content-disposition" in resp.headers["access-control-expose-headers"].lower()


def test_cors_ignores_unknown_origin(client):
    resp = preflight(client, "http://evil.example")
    assert "access-control-allow-origin" not in resp.headers
