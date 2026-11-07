"""DB cho test: SQLite in-memory dùng chung một kết nối; JSONB của Postgres chạy như JSON.

Schema thật (Postgres) được kiểm riêng ở tests/unit/test_db_schema.py.
"""

from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 – đăng ký mọi bảng
from app.db.base import Base


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):
    return "JSON"


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session


# Every key .env.example documents, so a new key is stripped without editing this file. The app no longer loads .env
# on import, but a key can still come from the shell (export, `uv run --env-file`); only `eval` / `acceptance` tests
# may use them (both are deselected by addopts and run on purpose with `uv run --env-file .env pytest -m ...`).
ENV_FILE_KEYS = tuple(dotenv_values(Path(__file__).parents[1] / ".env.example"))


@pytest.fixture(autouse=True)
def _no_env_file_keys(request, monkeypatch):
    """CLAUDE.md rule 9: a plain test must never reach the shared Qdrant cluster or a paid API."""
    if not any(request.node.get_closest_marker(m) for m in ("eval", "acceptance")):
        for key in ENV_FILE_KEYS:
            monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _no_rag_warmup(monkeypatch):
    """Test không bao giờ nạp bộ nhúng thật lúc startup; test warm-up tự bật lại."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "rag_warmup", False)
