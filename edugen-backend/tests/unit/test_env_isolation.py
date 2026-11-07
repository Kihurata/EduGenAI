"""Tóm tắt: test thường không bao giờ thấy khoá trong .env (CLAUDE.md quy tắc 9), để không chạm Qdrant Cloud dùng chung hay gọi
API trả phí. Import app không được nạp .env; khoá có sẵn trong shell thì fixture ở tests/conftest.py gỡ đi. Chỉ test đánh dấu
`eval` hoặc `acceptance` mới dùng .env."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import ENV_FILE_KEYS

ROOT = Path(__file__).parents[2]
SECRETS = ("QDRANT_URL", "QDRANT_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER",
           "GEMINI_MODEL", "EMBEDDER")


@pytest.mark.parametrize("name", SECRETS)
def test_unit_tests_never_see_env_file_keys(name):
    assert name in ENV_FILE_KEYS, f"{name} is not in .env.example, so tests/conftest.py would not strip it"
    assert name not in os.environ


def test_importing_the_app_never_loads_dotenv():
    """Importing the app must not push .env into os.environ: that is a side effect every importer (tests, scripts)
    inherits. Local runs load it on purpose with `uv run --env-file .env ...`; Docker passes it with env_file."""
    probe = (
        "import sys, dotenv\n"
        "calls = []\n"
        "dotenv.load_dotenv = lambda *a, **k: calls.append(a) or True\n"
        "import app.main  # noqa: F401\n"
        "sys.exit(len(calls))\n"
    )
    done = subprocess.run(  # check=False: the exit code is the number of calls, read below
        [sys.executable, "-c", probe], check=False, cwd=ROOT, env=dict(os.environ), capture_output=True, text=True
    )

    assert done.returncode == 0, f"load_dotenv() called {done.returncode} time(s) on import\n{done.stderr[-2000:]}"
