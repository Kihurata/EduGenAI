"""Đăng nhập JWT, refresh token, khóa tài khoản và admin quản lý giáo viên trong trường."""

from tests.api.conftest import PASSWORD, add_user, login


def post_login(client, email, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_login_and_me(client, teacher):
    resp = post_login(client, "GV1@nd.vn")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer" and body["refresh_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "gv1@nd.vn"
    assert me.json()["role"] == "teacher"
    assert me.json()["school"]["name"] == "THPT Nguyễn Du"


def test_wrong_password_or_unknown_email(client, teacher):
    assert post_login(client, "gv1@nd.vn", "sai").status_code == 401
    resp = post_login(client, "khong@nd.vn")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Email hoặc mật khẩu không đúng"


def test_missing_or_bad_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer rac"}).status_code == 401


def test_locked_account_cannot_login(client, db, school):
    add_user(db, school, "khoa@nd.vn", active=False)
    resp = post_login(client, "khoa@nd.vn")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Tài khoản đã bị khóa"


def test_refresh_rotates_and_logout_revokes(client, teacher):
    refresh = post_login(client, "gv1@nd.vn").json()["refresh_token"]
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    new_refresh = resp.json()["refresh_token"]
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": refresh}).status_code == 401
    assert client.post("/api/v1/auth/logout", json={"refresh_token": new_refresh}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh}).status_code == 401


def test_admin_creates_lists_and_locks_teachers(client, admin_headers):
    resp = client.post(
        "/api/v1/admin/teachers",
        json={"email": "Moi@ND.vn", "full_name": "Cô Mới", "password": "mat-khau-moi"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    teacher = resp.json()
    assert (teacher["email"], teacher["role"], teacher["is_active"]) == ("moi@nd.vn", "teacher", True)

    listed = client.get("/api/v1/admin/teachers", headers=admin_headers).json()
    assert [t["email"] for t in listed] == ["moi@nd.vn"]

    headers = {"Authorization": "Bearer " + post_login(client, "moi@nd.vn", "mat-khau-moi").json()["access_token"]}
    resp = client.patch(f"/api/v1/admin/teachers/{teacher['id']}", json={"is_active": False}, headers=admin_headers)
    assert resp.json()["is_active"] is False
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 403  # token cũ hết dùng được
    assert post_login(client, "moi@nd.vn", "mat-khau-moi").status_code == 403


def test_duplicate_teacher_email(client, admin_headers, teacher):
    resp = client.post(
        "/api/v1/admin/teachers",
        json={"email": "gv1@nd.vn", "full_name": "Trùng", "password": "mat-khau-moi"},
        headers=admin_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Email đã được dùng"


def test_teacher_cannot_use_admin_api(client, teacher_headers):
    resp = client.get("/api/v1/admin/teachers", headers=teacher_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Chỉ admin được dùng chức năng này"


def test_admin_cannot_touch_teachers_of_another_school(client, db, admin_headers, outsider_headers):
    other_admin = login(client, "admin@lqd.vn")
    outsiders = client.get("/api/v1/admin/teachers", headers=other_admin).json()
    assert [t["email"] for t in outsiders] == ["gv@lqd.vn"]
    assert client.get("/api/v1/admin/teachers", headers=admin_headers).json() == []
    resp = client.patch(f"/api/v1/admin/teachers/{outsiders[0]['id']}", json={"is_active": False}, headers=admin_headers)
    assert resp.status_code == 404
