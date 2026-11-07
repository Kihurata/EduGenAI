"""Tóm tắt: unit test phần SymPy của bộ sinh câu (T-031, F-04): schema bắt câu trả lời ngắn có sympy.expr, trắc nghiệm cho phép null, Đ/S không có; system prompt hướng dẫn viết biểu thức SymPy."""

import pytest

from app.rag.generation.generate import SCHEMAS, SYSTEM_PROMPT


def _item(qtype):
    return SCHEMAS[qtype]["properties"]["questions"]["items"]


def test_short_answer_schema_requires_sympy_expr():
    item = _item("short_answer")
    assert "sympy" in item["required"]
    assert item["properties"]["sympy"] == {"type": "object", "properties": {"expr": {"type": "string"}},
                                           "required": ["expr"], "additionalProperties": False}


def test_multiple_choice_schema_has_nullable_sympy_expr():
    item = _item("multiple_choice")
    assert "sympy" in item["required"]
    assert item["properties"]["sympy"]["properties"]["expr"] == {"anyOf": [{"type": "string"}, {"type": "null"}]}


def test_true_false_schema_has_no_sympy():
    assert "sympy" not in _item("true_false")["properties"]


def test_system_prompt_asks_for_sympy_expression():
    assert "sympy.expr" in SYSTEM_PROMPT and "Rational" in SYSTEM_PROMPT and "**" in SYSTEM_PROMPT


@pytest.mark.parametrize("hint", ["không dùng ^", "không chứa biến tự do", "Integral", "sqrt", "pi"])
def test_system_prompt_names_the_rules_verify_relies_on(hint):
    assert hint in SYSTEM_PROMPT


def test_system_prompt_states_the_4_box_short_answer_rule():
    assert "tối đa 4 kí tự" in SYSTEM_PROMPT
