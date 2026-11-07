"""Phiên đăng nhập: đổi mật khẩu, đăng xuất mọi thiết bị, token cũ mất hiệu lực, băm lại hash cũ."""

import importlib
from datetime import UTC, datetime

from sqlalchemy import func, select, update

from app.api.v1 import auth
from app.core import security
from app.core.config import settings
from app.models import RefreshToken, User
from tests.api.conftest import PASSWORD, login

NEW_PASSWORD = "matkhau-moi-456"


def post_login(client, email, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def change_password(client, headers, current=PASSWORD, new=NEW_PASSWORD):
    return client.post(
        "/api/v1/auth/change-password", headers=headers,
        json={"current_password": current, "new_password": new},
    )  # fmt: skip


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_change_password_logs_out_other_sessions(client, teacher):
    other = post_login(client, "gv1@nd.vn").json()
    current = post_login(client, "gv1@nd.vn").json()
    resp = change_password(client, bearer(current["access_token"]))
    assert resp.status_code == 200
    fresh = resp.json()
    # Phiên hiện tại tiếp tục bằng cặp token mới.
    assert client.get("/api/v1/auth/me", headers=bearer(fresh["access_token"])).status_code == 200
    # Access token và refresh token cũ (mọi thiết bị) mất hiệu lực ngay.
    for old in (other, current):
        assert client.get("/api/v1/auth/me", headers=bearer(old["access_token"])).status_code == 401
        refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": old["refresh_token"]})
        assert refreshed.status_code == 401
    assert post_login(client, "gv1@nd.vn").status_code == 401
    assert post_login(client, "gv1@nd.vn", NEW_PASSWORD).status_code == 200


def test_change_password_rejects_wrong_or_same_or_short(client, teacher_headers):
    assert change_password(client, teacher_headers, current="sai").status_code == 400
    assert change_password(client, teacher_headers, new=PASSWORD).status_code == 400
    assert change_password(client, teacher_headers, new="ngan").status_code == 422
    assert change_password(client, teacher_headers, new="x" * 257).status_code == 422


def test_change_password_wrong_current_is_throttled(client, teacher_headers, monkeypatch):
    monkeypatch.setattr(settings, "login_max_failures", 2)
    for _ in range(2):
        assert change_password(client, teacher_headers, current="sai").status_code == 400
    assert change_password(client, teacher_headers).status_code == 429


def test_admin_password_reset_invalidates_teacher_access_token(client, teacher, admin_headers):
    teacher_headers = login(client, "gv1@nd.vn")
    resp = client.patch(
        f"/api/v1/admin/teachers/{teacher.id}", headers=admin_headers, json={"password": NEW_PASSWORD}
    )
    assert resp.status_code == 200
    assert client.get("/api/v1/auth/me", headers=teacher_headers).status_code == 401


def test_logout_all_revokes_every_refresh_token(client, teacher):
    first = post_login(client, "gv1@nd.vn").json()
    second = post_login(client, "gv1@nd.vn").json()
    resp = client.post("/api/v1/auth/logout-all", headers=bearer(first["access_token"]))
    assert resp.status_code == 204
    for pair in (first, second):
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}).status_code == 401


def test_refresh_lost_race_does_not_issue_tokens(client, db, teacher, monkeypatch):
    pair = post_login(client, "gv1@nd.vn").json()
    assert post_login(client, "gv1@nd.vn").status_code == 200  # phiên khác của cùng user
    original_find_refresh = auth._find_refresh
    original_issue = auth._issue
    issue_calls = 0

    def lose_race(session, token):
        row = original_find_refresh(session, token)
        session.execute(
            update(RefreshToken).where(RefreshToken.id == row.id).values(revoked_at=datetime.now(UTC)),
            execution_options={"synchronize_session": False},
        )
        session.commit()
        return row

    def track_issue(session, user):
        nonlocal issue_calls
        issue_calls += 1
        return original_issue(session, user)

    monkeypatch.setattr(auth, "_find_refresh", lose_race)
    monkeypatch.setattr(auth, "_issue", track_issue)

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})

    assert response.status_code == 401
    assert issue_calls == 0
    assert "access_token" not in response.json()
    count = db.scalar(select(func.count()).select_from(RefreshToken).where(RefreshToken.user_id == teacher.id))
    assert count == 2
    # Lost race được xử lý như reuse: các phiên khác của user cũng bị thu hồi.
    db.expire_all()
    live = db.scalar(
        select(func.count())
        .select_from(RefreshToken)
        .where(RefreshToken.user_id == teacher.id, RefreshToken.revoked_at.is_(None))
    )
    assert live == 0


def test_token_without_password_fingerprint_is_rejected(client, teacher):
    token = security.create_access_token(str(teacher.id))  # không có pwv
    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 401


def test_login_upgrades_weak_hash(client, db, teacher, monkeypatch):
    old_hash = teacher.password_hash  # 1000 vòng (fixture)
    monkeypatch.setattr(settings, "password_hash_iterations", 2000)
    assert post_login(client, "gv1@nd.vn").status_code == 200
    db.expire_all()
    new_hash = db.get(User, teacher.id).password_hash
    assert new_hash != old_hash and new_hash.startswith("pbkdf2_sha256$2000$")
    assert post_login(client, "gv1@nd.vn").status_code == 200


def test_expired_refresh_tokens_are_pruned_on_issue(client, db, teacher, monkeypatch):
    monkeypatch.setattr(settings, "refresh_token_days", -1)  # token sinh ra đã hết hạn
    post_login(client, "gv1@nd.vn")
    post_login(client, "gv1@nd.vn")
    monkeypatch.setattr(settings, "refresh_token_days", 14)
    post_login(client, "gv1@nd.vn")
    count = db.scalar(select(func.count()).select_from(RefreshToken).where(RefreshToken.user_id == teacher.id))
    assert count == 1


def test_docs_hidden_outside_dev(monkeypatch):
    from app import main

    monkeypatch.setattr(settings, "app_env", "production")
    try:
        prod = importlib.reload(main).app
        assert prod.openapi_url is None and prod.docs_url is None
    finally:
        monkeypatch.setattr(settings, "app_env", "dev")
        importlib.reload(main)
