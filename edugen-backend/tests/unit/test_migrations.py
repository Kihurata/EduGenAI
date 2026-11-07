"""Migration Alembic phải khớp model: sửa model mà quên tạo migration thì test này đỏ.

Chạy trên SQLite (JSONB → JSON qua hook trong conftest), không so kiểu cột vì SQLite
không giữ kiểu Postgres; kiểu cột được `alembic check` trên Postgres thật kiểm.
"""

import os
import uuid
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

import app.models  # noqa: F401 – đăng ký mọi bảng
from alembic import command
from app.db.base import Base

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")
BACKEND = Path(__file__).resolve().parents[2]


def _alembic_config(connection) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.attributes["connection"] = connection
    return cfg


def test_upgrade_head_matches_models(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'mig.db'}")
    with engine.begin() as conn:
        command.upgrade(_alembic_config(conn), "head")
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_downgrade_base_removes_all_tables(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'mig.db'}")
    with engine.begin() as conn:
        cfg = _alembic_config(conn)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        assert set(inspect(conn).get_table_names()) <= {"alembic_version"}


def _db_indexes(conn) -> set[tuple[str, str]]:
    insp = inspect(conn)
    return {
        (t, ix["name"])
        for t in insp.get_table_names()
        for ix in insp.get_indexes(t)
        if not ix["name"].startswith("sqlite_")
    }


def _model_indexes() -> set[tuple[str, str]]:
    # Index tường minh + index=True; unique constraint không tính (SQLite/PG liệt kê khác nhau).
    return {(t.name, ix.name) for t in Base.metadata.tables.values() for ix in t.indexes}


def test_upgrade_head_creates_exactly_the_model_indexes(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'mig.db'}")
    with engine.begin() as conn:
        command.upgrade(_alembic_config(conn), "head")
        db = {(t, n) for t, n in _db_indexes(conn)}
    # unique=True sinh index duy nhất trong DB; chỉ so các index không unique.
    assert _model_indexes() <= db
    assert not {n for _, n in db if n.endswith("_status")}


LEGACY_STATUS_INDEXES = [
    ("exams", "ix_exams_status"),
    ("exam_matrices", "ix_exam_matrices_status"),
    ("sample_exams", "ix_sample_exams_status"),
]


def test_stamp_baseline_then_upgrade_drops_legacy_status_indexes(tmp_path):
    """DB dựng bằng create_all từ trước PR này có index status; stamp 0001 rồi upgrade phải gỡ."""
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        Base.metadata.create_all(conn)
        for table, name in LEGACY_STATUS_INDEXES:
            conn.exec_driver_sql(f"CREATE INDEX {name} ON {table} (status)")
        cfg = _alembic_config(conn)
        command.stamp(cfg, "0001")
        command.upgrade(cfg, "head")
        assert not {n for _, n in _db_indexes(conn) if n.endswith("_status")}
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []


def test_downgrade_to_baseline_restores_legacy_status_indexes(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'mig.db'}")
    with engine.begin() as conn:
        cfg = _alembic_config(conn)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "0001")
        assert set(LEGACY_STATUS_INDEXES) <= _db_indexes(conn)


@pytest.mark.skipif(not POSTGRES_URL, reason="đặt TEST_POSTGRES_URL tới một server Postgres để chạy")
def test_postgres_upgrade_check_downgrade():
    """Trên Postgres thật: ENUM, JSONB, ràng buộc, kiểu cột khớp model; downgrade dọn sạch.

    Chạy trong một database tạm (tạo qua kết nối của TEST_POSTGRES_URL, xóa khi xong)
    nên không đụng dữ liệu của database mà URL trỏ tới.
    """
    base = make_url(POSTGRES_URL)
    name = f"edugen_migtest_{uuid.uuid4().hex[:10]}"
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = create_engine(base.set(database=name))
    try:
        with engine.begin() as conn:
            cfg = _alembic_config(conn)
            command.upgrade(cfg, "head")
            ctx = MigrationContext.configure(conn, opts={"compare_type": True})
            assert compare_metadata(ctx, Base.metadata) == []
            assert _model_indexes() <= _db_indexes(conn)
            command.downgrade(cfg, "base")
            assert set(inspect(conn).get_table_names()) <= {"alembic_version"}
            enums = conn.exec_driver_sql("SELECT typname FROM pg_type WHERE typtype = 'e'").all()
            assert enums == []
    finally:
        engine.dispose()
        with admin.connect() as c:
            c.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.dispose()


def _insert_draft(conn, grade, exam_kind):
    import json

    from sqlalchemy import text

    row_id = uuid.uuid4().hex
    conn.execute(text(
        "INSERT INTO sample_exams (id, school_id, uploaded_by, subject_id, grade, title, original_filename, mime_type,"
        " size_bytes, storage_key, checksum_sha256, status, draft, created_at, updated_at) VALUES (:id, :s, :u, :sub,"
        " :grade, 't', 'de.pdf', 'application/pdf', 1, :key, :key, 'NEEDS_REVIEW', :draft, CURRENT_TIMESTAMP,"
        " CURRENT_TIMESTAMP)"
    ), {"id": row_id, "s": uuid.uuid4().hex, "u": uuid.uuid4().hex, "sub": uuid.uuid4().hex, "grade": grade,
        "key": row_id, "draft": json.dumps({"exam": "Đề", "exam_kind": exam_kind, "questions": []})})  # fmt: skip
    return row_id


@pytest.mark.parametrize("old, grade, new", [("thi_thu", 12, "tot_nghiep"), ("dinh_ky", 11, "dinh_ky_7991"),
                                             ("khac", 12, "tot_nghiep"), ("khac", 10, "dinh_ky_7991")])  # fmt: skip
def test_TC_028_upgrade_moves_old_draft_exam_kinds_to_d017(tmp_path, old, grade, new):
    import json

    from sqlalchemy import text

    engine = create_engine(f"sqlite:///{tmp_path / 'mig.db'}")
    with engine.begin() as conn:
        cfg = _alembic_config(conn)
        command.upgrade(cfg, "0003")
        row_id = _insert_draft(conn, grade, old)
        command.upgrade(cfg, "head")
        draft = conn.execute(text("SELECT draft FROM sample_exams WHERE id = :id"), {"id": row_id}).scalar_one()
    assert json.loads(draft)["exam_kind"] == new
