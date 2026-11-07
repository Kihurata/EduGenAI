"""Băm mật khẩu, JWT và lệnh seed tạo trường + admin đầu tiên."""

import secrets

import pytest
from sqlalchemy import select

from app.core import security
from app.core.config import settings
from app.models import Subject, User
from app.models.enums import UserRole
from app.seed import seed

ADMIN_PW = secrets.token_hex(8)  # random per run, no credential literal


@pytest.fixture(autouse=True)
def fast_hash(monkeypatch):
    monkeypatch.setattr(settings, "password_hash_iterations", 1000)


def test_password_hash_round_trip():
    hashed = security.hash_password("bí mật")
    assert hashed.startswith("pbkdf2_sha256$1000$")
    assert security.verify_password("bí mật", hashed)
    assert not security.verify_password("sai", hashed)
    assert hashed != security.hash_password("bí mật")  # salt ngẫu nhiên


def test_access_token_round_trip_and_tampering():
    token = security.create_access_token("u1")
    assert security.decode_access_token(token) == "u1"
    assert security.decode_access_token(token + "x") is None


def test_expired_access_token_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "access_token_minutes", -1)
    assert security.decode_access_token(security.create_access_token("u1")) is None


def test_seed_creates_school_admin_and_math_subject(db):
    school, admin = seed(db, "nd", "THPT Nguyễn Du", "Admin@ND.vn ", ADMIN_PW, "Quản trị")
    assert (school.code, school.name) == ("nd", "THPT Nguyễn Du")
    assert (admin.email, admin.role, admin.school_id) == ("admin@nd.vn", UserRole.admin, school.id)
    assert security.verify_password(ADMIN_PW, admin.password_hash)
    assert db.scalar(select(Subject.name).where(Subject.code == "toan")) == "Toán học"


def test_seed_creates_physics_and_chemistry_subjects(db):
    seed(db, "nd", "THPT Nguyễn Du", "admin@nd.vn", ADMIN_PW, "Quản trị")
    names = dict(db.execute(select(Subject.code, Subject.name)).all())
    assert names == {"toan": "Toán học", "ly": "Vật lí", "hoa": "Hoá học"}


def test_seed_second_school_reuses_subject_and_rejects_duplicates(db):
    seed(db, "nd", "THPT Nguyễn Du", "admin@nd.vn", ADMIN_PW, "A")
    seed(db, "lqd", "THPT Lê Quý Đôn", "admin@lqd.vn", ADMIN_PW, "B")
    assert len(db.scalars(select(Subject)).all()) == 3
    with pytest.raises(ValueError, match="đã tồn tại"):
        seed(db, "nd", "Trùng", "khac@nd.vn", ADMIN_PW, "C")
    with pytest.raises(ValueError, match="đã được dùng"):
        seed(db, "moi", "Mới", "admin@nd.vn", ADMIN_PW, "D")
    assert len(db.scalars(select(User)).all()) == 2


def test_seed_if_missing_creates_then_is_a_noop(db):
    from app.seed import seed_if_missing

    args = ("nd", "THPT Nguyễn Du", "admin@nd.vn", ADMIN_PW, "Quản trị")
    assert seed_if_missing(db, *args) is not None
    assert seed_if_missing(db, *args) is None  # lần hai: không đổi gì, không lỗi
    assert len(db.scalars(select(User)).all()) == 1


def test_seed_if_missing_skips_when_only_email_exists(db):
    from app.seed import seed_if_missing

    seed(db, "nd", "THPT Nguyễn Du", "admin@nd.vn", ADMIN_PW, "A")
    assert seed_if_missing(db, "khac", "Khác", "admin@nd.vn", ADMIN_PW, "B") is None
    assert len(db.scalars(select(User)).all()) == 1


def test_seed_cli_reads_env_and_if_missing_exits_cleanly(db, monkeypatch, capsys):
    from contextlib import nullcontext

    import app.db.session as session_mod
    from app import seed as seed_mod

    monkeypatch.setattr(session_mod, "SessionLocal", lambda: nullcontext(db))
    for key, value in {
        "SEED_SCHOOL_CODE": "nd", "SEED_SCHOOL_NAME": "THPT Nguyễn Du", "SEED_ADMIN_EMAIL": "admin@nd.vn",
        "SEED_ADMIN_NAME": "Quản trị", "SEED_ADMIN_PASSWORD": ADMIN_PW,
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("sys.argv", ["seed", "--if-missing"])
    seed_mod.main()
    seed_mod.main()  # lần hai không ném lỗi
    assert "đã có" in capsys.readouterr().out
    assert len(db.scalars(select(User)).all()) == 1
