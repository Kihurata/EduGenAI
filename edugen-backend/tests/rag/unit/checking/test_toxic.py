"""Tóm tắt: guardrail T-038: câu sinh ra có từ cấm (danh sách từ) bị loại với lỗi toxic_content; tìm cả trong đề, phương án, ý Đ/S và lời giải, không phân biệt hoa thường, chỉ khớp nguyên từ."""

import copy

import pytest

from app.rag.checking import CHECKS, check
from app.rag.checking.toxic import check_toxic
from tests.rag.support import LLM_OUTPUT


def _q(qtype="multiple_choice", **over):
    return copy.deepcopy(LLM_OUTPUT[qtype]) | {"type": qtype, "level": "Biết", "topic": "t"} | over


def test_clean_question_has_no_toxic_error():
    for qtype in LLM_OUTPUT:
        assert check_toxic(_q(qtype), None) == [], qtype


@pytest.mark.parametrize("field, value", [
    ("stem", "Đồ ngu, tính đạo hàm của $x^2$."),
    ("explanation", "Vì FUCK $(x^2)'=2x$."),
    ("options", {"A": "$2x$", "B": "đồ khốn", "C": "$2$", "D": "$x^2$"}),
])
def test_banned_word_anywhere_in_the_question_is_toxic_content(field, value):
    errors = check_toxic(_q(**{field: value}), None)

    assert len(errors) == 1 and errors[0].startswith("toxic_content")


def test_banned_word_in_a_true_false_statement_is_toxic_content():
    q = _q("true_false")
    q["statements"][2]["text"] = "Thằng ngu cũng biết ý này đúng."

    assert check_toxic(q, None)[0].startswith("toxic_content")


def test_banned_word_inside_another_word_is_not_flagged():
    assert check_toxic(_q(stem="Tính shitake? Không: tính $\\int_0^1 x\\,dx$."), None) == []


def test_toxic_check_runs_with_the_other_checks():
    assert check_toxic in CHECKS
    assert any(e.startswith("toxic_content") for e in check(_q(stem="đồ ngu"), {"t1"}))
