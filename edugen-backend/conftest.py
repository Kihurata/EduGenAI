"""Tóm tắt: chia test thành từng bộ (suite) theo chức năng, đọc từ tests/features.yaml.

    uv run pytest --list-suites            # các bộ và số test mỗi bộ
    uv run pytest --suite F-03             # chỉ bộ F-03 (lặp --suite để chạy nhiều bộ)
    uv run pytest --suite F-03 -m unit     # một bộ, một mức (unit | integration | acceptance | eval)
"""

from pathlib import Path

import pytest
import yaml

LEVELS = ("unit", "integration", "acceptance", "eval")
SUITES = yaml.safe_load((Path(__file__).parent / "tests" / "features.yaml").read_text(encoding="utf-8"))["features"]
# Most specific entry first, so `file::test` beats `file`.
ENTRIES = sorted(
    ((path, suite, level) for suite, spec in SUITES.items() for level in LEVELS for path in spec.get(level) or []),
    key=lambda e: -len(e[0]),
)


def suite_of(nodeid):
    for path, suite, level in ENTRIES:
        if nodeid == path or nodeid.startswith((path + "::", path + "[")):
            return suite, level
    return "unmapped", None


def pytest_addoption(parser):
    parser.addoption("--suite", action="append", default=[], help="run only this feature suite (e.g. F-03)")
    parser.addoption("--list-suites", action="store_true", help="list feature suites and their test counts")


def pytest_configure(config):
    for level in LEVELS:
        config.addinivalue_line("markers", f"{level}: {level} test (from tests/features.yaml)")
    unknown = set(config.getoption("--suite")) - set(SUITES) - {"unmapped"}
    if unknown:
        raise pytest.UsageError(f"unknown suite(s) {sorted(unknown)}; choose from {list(SUITES)}")


@pytest.hookimpl(tryfirst=True)  # add level markers before `-m` deselects
def pytest_collection_modifyitems(config, items):
    wanted = set(config.getoption("--suite"))
    keep, drop = [], []
    for item in items:
        item.suite, level = suite_of(item.nodeid)
        if level:
            item.add_marker(level)
        (keep if not wanted or item.suite in wanted else drop).append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep


def pytest_collection_finish(session):
    if not session.config.getoption("--list-suites"):
        return
    counts = {}
    for item in session.items:
        counts[item.suite] = counts.get(item.suite, 0) + 1
    print("\nsuite                count  title")
    for suite in [*SUITES, "unmapped"]:
        title = SUITES.get(suite, {}).get("title", "not in tests/features.yaml")
        print(f"{suite:<20} {counts.get(suite, 0):>5}  {title}")
    session.items.clear()  # list only, run nothing


def pytest_sessionfinish(session):
    if session.config.getoption("--list-suites"):
        session.exitstatus = pytest.ExitCode.OK  # not "no tests ran"
