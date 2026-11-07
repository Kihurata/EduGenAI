"""Tóm tắt: unit test các ma trận đề Toán 12 dạng YAML (T-027): mỗi ma trận đúng cấu trúc đề tốt nghiệp (12 câu Phần I, 4 câu Đ/S × 4 ý, 6 câu trả lời ngắn), phần khớp dạng câu, mã chủ đề và mức độ đều có trong bộ từ vựng chung, và ghi rõ nguồn, độ tin cậy, chính thức hay không."""

from collections import Counter
from pathlib import Path

import pytest
import yaml

from app.rag.vocab import LEVEL_FROM_CODE, PART_BY_TYPE, TOPICS
from tests.rag.support import FIXTURES

MATRICES = sorted((FIXTURES / "toan-matrix").glob("*.yaml"))


def _matrix(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))["matrix"]


def test_there_are_five_toan_matrices():
    assert [p.stem for p in MATRICES] == ["derived-tn-2025-0101", "derived-tn-2026-0102", "mathvn-tn-2025",
                                          "viasm-pa1", "viasm-pa2"]


@pytest.mark.parametrize("path", MATRICES, ids=lambda p: p.stem)
def test_matrix_has_the_graduation_exam_shape(path):
    items = Counter()
    for cell in _matrix(path)["cells"]:
        items[cell["type"]] += cell["count"]

    assert items == {"multiple_choice": 12, "true_false": 16, "short_answer": 6}  # QĐ 764: 12 + 4×4 + 6


@pytest.mark.parametrize("path", MATRICES, ids=lambda p: p.stem)
def test_every_cell_sits_in_the_part_of_its_type(path):
    assert all(cell["part"] == PART_BY_TYPE[cell["type"]] for cell in _matrix(path)["cells"])


@pytest.mark.parametrize("path", MATRICES, ids=lambda p: p.stem)
def test_every_true_false_question_has_four_statements(path):
    statements = Counter()
    for cell in _matrix(path)["cells"]:
        if cell["type"] == "true_false":
            statements[cell["question"]] += cell["count"]

    assert sorted(statements) == [1, 2, 3, 4] and set(statements.values()) == {4}


@pytest.mark.parametrize("path", MATRICES, ids=lambda p: p.stem)
def test_topics_are_known_codes_and_levels_known_spellings(path):
    for cell in _matrix(path)["cells"]:
        if "topic" in cell:
            assert f"{cell['strand']}/{cell['topic']}" in TOPICS, cell
        if "level" in cell:
            assert cell["level"] in LEVEL_FROM_CODE, cell
        assert cell["count"] >= 1


@pytest.mark.parametrize("path", MATRICES, ids=lambda p: p.stem)
def test_matrix_states_its_source_and_confidence(path):
    m = _matrix(path)

    assert (m["subject"], m["grade"], m["exam_kind"]) == ("toan", 12, "tot_nghiep")
    assert m["source"] and m["confidence"] in {"high", "medium", "unknown"} and isinstance(m["official"], bool)
