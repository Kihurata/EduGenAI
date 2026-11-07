"""Gia cố bảo mật: chặn dò mật khẩu, refresh token bị dùng lại, header bảo mật, giới hạn upload."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import DEV_JWT_SECRET, Settings, settings
from app.core.security import ALGORITHM, decode_access_token
from tests.api.conftest import MATRIX_PNG, PASSWORD


def post_login(client, email, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_too_many_failed_logins_are_throttled(client, teacher, monkeypatch):
    monkeypatch.setattr(settings, "login_max_failures", 3)
    for _ in range(3):
        assert post_login(client, "gv1@nd.vn", "sai").status_code == 401
    blocked = post_login(client, "gv1@nd.vn")  # đúng mật khẩu vẫn bị chặn trong cửa sổ
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    # Email khác không bị ảnh hưởng.
    assert post_login(client, "admin@nd.vn").status_code == 200


def test_successful_login_resets_failure_count(client, teacher, monkeypatch):
    monkeypatch.setattr(settings, "login_max_failures", 3)
    for _ in range(2):
        post_login(client, "gv1@nd.vn", "sai")
    assert post_login(client, "gv1@nd.vn").status_code == 200
    for _ in range(2):
        post_login(client, "gv1@nd.vn", "sai")
    assert post_login(client, "gv1@nd.vn").status_code == 200


def test_unknown_email_also_counts_toward_throttle(client, monkeypatch):
    monkeypatch.setattr(settings, "login_max_failures", 2)
    for _ in range(2):
        assert post_login(client, "khong@nd.vn").status_code == 401
    assert post_login(client, "khong@nd.vn").status_code == 429


def test_reused_refresh_token_revokes_all_sessions(client, teacher):
    first = post_login(client, "gv1@nd.vn").json()["refresh_token"]
    other_device = post_login(client, "gv1@nd.vn").json()["refresh_token"]
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": first}).json()["refresh_token"]
    # Kẻ trộm gửi lại token cũ → mọi phiên bị thu hồi.
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first}).status_code == 401
    for token in (rotated, other_device):
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": token}).status_code == 401


def test_security_headers_and_no_store_on_auth(client, teacher):
    health = client.get("/health")
    assert health.headers["X-Content-Type-Options"] == "nosniff"
    assert health.headers["X-Frame-Options"] == "DENY"
    assert "no-store" not in health.headers.get("Cache-Control", "")
    assert post_login(client, "gv1@nd.vn").headers["Cache-Control"] == "no-store"


def test_token_without_exp_is_rejected():
    token = jwt.encode({"sub": "abc"}, settings.jwt_secret, algorithm=ALGORITHM)
    assert decode_access_token(token) is None
    expired = jwt.encode(
        {"sub": "abc", "exp": datetime.now(UTC) - timedelta(seconds=1)}, settings.jwt_secret, algorithm=ALGORITHM
    )
    assert decode_access_token(expired) is None


def test_oversized_login_payload_is_rejected(client):
    assert post_login(client, "gv1@nd.vn", "x" * 10_000).status_code == 422


def test_upload_over_limit_is_rejected(client, teacher_headers, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 0)  # mọi file khác rỗng đều quá giới hạn
    resp = client.post(
        "/api/v1/matrices", headers=teacher_headers,
        files={"file": ("m.png", MATRIX_PNG.read_bytes(), "image/png")},
    )  # fmt: skip
    assert resp.status_code == 413


def test_non_dev_env_requires_real_secret():
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(app_env="production", jwt_secret=DEV_JWT_SECRET)
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(app_env="production", jwt_secret="ngan")
    assert Settings(app_env="production", jwt_secret="x" * 32).app_env == "production"
