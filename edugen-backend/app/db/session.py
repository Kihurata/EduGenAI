from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session_factory() -> sessionmaker:
    """Dependency cho FastAPI; job nền mở session riêng từ đây. Test override hàm này."""
    return SessionLocal


def get_db(factory: sessionmaker = Depends(get_session_factory)) -> Iterator[Session]:  # noqa: B008 - FastAPI DI
    """Dependency cho FastAPI: mỗi request một session."""
    with factory() as session:
        yield session
