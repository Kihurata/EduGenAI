"""Tóm tắt: kiểm tra tests/features.yaml luôn khớp với code: mọi file test đều thuộc một bộ, mọi mục đều trỏ tới test có thật."""

import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
LEVELS = ("unit", "integration", "acceptance", "eval")
SUITES = yaml.safe_load((ROOT / "tests" / "features.yaml").read_text(encoding="utf-8"))["features"]
ENTRIES = [p for spec in SUITES.values() for level in LEVELS for p in spec.get(level) or []]


def defined_tests(path):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    return {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")}


def test_every_test_file_belongs_to_a_suite():
    files = {p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").rglob("test_*.py")}
    mapped = {e.split("::")[0] for e in ENTRIES}
    assert sorted(files - mapped) == []


def test_every_entry_points_at_an_existing_test():
    broken = []
    for entry in ENTRIES:
        path, _, name = entry.partition("::")
        if not (ROOT / path).is_file() or (name and name not in defined_tests(path)):
            broken.append(entry)
    assert broken == []


def test_no_entry_is_listed_twice():
    assert sorted({e for e in ENTRIES if ENTRIES.count(e) > 1}) == []
