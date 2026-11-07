"""Alembic env: schema lấy từ app.models, URL lấy từ DATABASE_URL như app."""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

import app.models  # noqa: F401 – đăng ký mọi bảng vào Base.metadata
from alembic import context
from app.core.config import settings
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    # Giữ logger của app (vd. audit `edugen.auth`) khi migration chạy trong cùng process.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: in SQL ra stdout, không cần kết nối DB."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Test truyền sẵn connection (SQLite) qua config.attributes.
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        _run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
