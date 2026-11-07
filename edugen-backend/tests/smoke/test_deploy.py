"""Tóm tắt: smoke test sau khi deploy lên cloud (T-042, F-18). Chạy với BASE_URL của server thật, không có BASE_URL thì bỏ qua.
"""

import os
import re
import socket
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
needs_server = pytest.mark.skipif(not BASE_URL, reason="đặt BASE_URL để chạy smoke test trên server thật")
needs_login = pytest.mark.skipif(
    not all(os.environ.get(k) for k in ("SMOKE_EMAIL", "SMOKE_PASSWORD", "SMOKE_MATRIX_ID")),
    reason="đặt SMOKE_EMAIL, SMOKE_PASSWORD, SMOKE_MATRIX_ID để chạy luồng chính",
)
REPO = Path(__file__).parents[3]


@needs_server
def test_health_answers_200_within_2_seconds():
    start = time.monotonic()
    resp = httpx.get(f"{BASE_URL}/health", timeout=5)
    assert resp.status_code == 200
    assert time.monotonic() - start < 2


@needs_server
def test_http_redirects_to_https_with_valid_certificate():
    host = urlsplit(BASE_URL).hostname
    resp = httpx.get(f"http://{host}/health", follow_redirects=False, timeout=5)
    assert resp.status_code in (301, 302, 307, 308)
    assert resp.headers["location"].startswith("https://")
    # verify=True (mặc định): chứng chỉ sai hoặc hết hạn sẽ ném lỗi
    assert httpx.get(f"https://{host}/health", timeout=5).status_code == 200


@needs_login
@needs_server
def test_main_flow_confirmed_matrix_to_22_question_docx():
    with httpx.Client(base_url=BASE_URL, timeout=120) as c:
        login = c.post("/api/v1/auth/login", json={"email": os.environ["SMOKE_EMAIL"], "password": os.environ["SMOKE_PASSWORD"]})
        assert login.status_code == 200, login.text
        c.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        created = c.post("/api/v1/exams", json={"matrix_id": os.environ["SMOKE_MATRIX_ID"], "duration_minutes": 45})
        assert created.status_code == 202, created.text
        exam_id = created.json()["id"]
        exam = {}
        for _ in range(60):  # job nền sinh đề
            exam = c.get(f"/api/v1/exams/{exam_id}").json()
            if exam["status"] != "generating":
                break
            time.sleep(2)
        assert exam["status"] == "generated", exam["status"]
        assert len(exam["questions"]) == 22
        assert c.post(f"/api/v1/exams/{exam_id}/approve").status_code == 200
        docx = c.get(f"/api/v1/exams/{exam_id}/export", params={"variant": "teacher"})
        assert docx.status_code == 200
        assert docx.content[:2] == b"PK"  # file DOCX là zip


@needs_server
def test_database_and_vector_store_ports_are_closed_to_internet():
    host = urlsplit(BASE_URL).hostname
    ports = [int(p) for p in os.environ.get("SMOKE_CLOSED_PORTS", "5432,6333,6334,8000").split(",")]
    open_ports = []
    for port in ports:
        with socket.socket() as s:
            s.settimeout(3)
            if s.connect_ex((host, port)) == 0:
                open_ports.append(port)
    assert open_ports == []


SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),  # Google / Gemini API key
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key
    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
    re.compile(r"(?im)^\s*(?:GEMINI_API_KEY|QDRANT_API_KEY|JWT_SECRET\w*)\s*=\s*[A-Za-z0-9_\-]{16,}\s*$"),
]
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "qdrant_data", "dev_data", "output", "dist"}
TEXT_SUFFIXES = {"", ".py", ".yml", ".yaml", ".toml", ".json", ".md", ".txt", ".sh", ".ts", ".tsx", ".env", ".example", ".ini"}


def test_no_secret_in_repo_files():
    hits = []
    for path in REPO.rglob("*"):
        if not path.is_file() or SKIP_DIRS & set(path.parts) or path.suffix not in TEXT_SUFFIXES:
            continue
        if path.name == ".env" or path.stat().st_size > 1_000_000:
            continue  # .env nằm trong .gitignore
        text = path.read_text(encoding="utf-8", errors="ignore")
        hits += [str(path.relative_to(REPO)) for p in SECRET_PATTERNS if p.search(text)]
    assert hits == []
