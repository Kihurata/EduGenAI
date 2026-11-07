import logging
import threading
import time

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import rag_client


def _fake_build(built, delay=0.0):
    def build():
        built.append(1)
        time.sleep(delay)
        return (lambda c: None), (lambda chunks: None), (lambda school_id, source=None: None)

    return build


def _setup(monkeypatch, built, delay=0.0, warmup=True):
    monkeypatch.setattr(settings, "rag_mock_samples", None)
    monkeypatch.setattr(settings, "rag_warmup", warmup)
    monkeypatch.setattr(rag_client, "_build_rag", _fake_build(built, delay))
    rag_client.local_rag.cache_clear()


def _wait_threads():
    for t in threading.enumerate():
        if t.name == "rag-warmup":
            t.join(5)


def test_startup_builds_rag_once_and_requests_reuse_it(monkeypatch):
    built = []
    _setup(monkeypatch, built)
    try:
        with TestClient(app) as c:
            _wait_threads()
            assert c.get("/health").status_code == 200
            rag_client.get_rag_client()
        assert built == [1]
    finally:
        rag_client.local_rag.cache_clear()


def test_concurrent_first_calls_build_once(monkeypatch):
    built = []
    _setup(monkeypatch, built, delay=0.2)
    try:
        results = []
        threads = [threading.Thread(target=lambda: results.append(rag_client.get_rag_client())) for _ in range(5)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert built == [1]
        assert len({id(r) for r in results}) == 1
    finally:
        rag_client.local_rag.cache_clear()


def test_startup_does_not_wait_for_slow_warmup(monkeypatch):
    built = []
    _setup(monkeypatch, built, delay=1.0)
    try:
        start = time.monotonic()
        with TestClient(app) as c:
            assert c.get("/health").status_code == 200
            assert time.monotonic() - start < 0.8
            _wait_threads()
    finally:
        rag_client.local_rag.cache_clear()


def test_warmup_disabled_builds_nothing(monkeypatch):
    built = []
    _setup(monkeypatch, built, warmup=False)
    try:
        with TestClient(app):
            _wait_threads()
        assert built == []
    finally:
        rag_client.local_rag.cache_clear()


def test_warmup_failure_logs_warning_and_does_not_crash(monkeypatch, caplog):
    monkeypatch.setattr(settings, "rag_warmup", True)
    monkeypatch.setattr(rag_client, "get_rag_client", lambda: (_ for _ in ()).throw(RuntimeError("thiếu khóa")))
    with caplog.at_level(logging.WARNING, logger="edugen.rag"), TestClient(app) as c:
        _wait_threads()
        assert c.get("/health").status_code == 200
    assert "thiếu khóa" in caplog.text
