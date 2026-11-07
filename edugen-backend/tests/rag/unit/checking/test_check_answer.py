"""Tóm tắt: unit test bước kiểm tra đáp số trong pipeline (T-031, F-04): câu trả lời ngắn phải có sympy.expr khớp đáp án; trắc nghiệm chỉ kiểm khi phương án đúng là số; Đ/S bỏ qua; luôn ghi sympy {expr, verified} lên câu. Viết lại từ các test SymPy trước đây đi qua pipeline, nay gọi thẳng check_answer."""

import copy

import pytest

from app.rag.checking.verify import check_answer
from tests.rag.support import LLM_OUTPUT


def _q(qtype, **over):
    return copy.deepcopy(LLM_OUTPUT[qtype]) | {"type": qtype, "level": "Biết", "topic": "t"} | over


NUMERIC_MC = {"options": {"A": "$-1,5$", "B": "$2$", "C": "$1.5$", "D": "$0$"}}


# --- short answer (every one is verified) ---------------------------------------------------------------------

def test_short_answer_verified_by_sympy_is_kept():
    q = _q("short_answer")

    assert check_answer(q) == []
    assert q["sympy"] == {"expr": "diff(x**2, x).subs(x, 1)", "verified": True}


def test_short_answer_sympy_disagrees_is_rejected_with_both_values():
    q = _q("short_answer", sympy={"expr": "1 + 2"})

    assert check_answer(q) == ["answer 2 but SymPy gives 3 for '1 + 2'"]
    assert q["sympy"]["verified"] is False


@pytest.mark.parametrize("sympy", [{"expr": ""}, {"expr": None}, {"expr": "   "}, {}, None, "missing"])
def test_short_answer_without_sympy_expr_is_rejected(sympy):
    q = _q("short_answer")
    if sympy == "missing":
        del q["sympy"]
    else:
        q["sympy"] = sympy

    assert check_answer(q) == ["no sympy.expr"]
    assert "sympy" not in q


def test_short_answer_unverifiable_expr_is_rejected_with_reason():
    q = _q("short_answer", sympy={"expr": "x + 1"})

    assert check_answer(q) == ["sympy.expr unverifiable: 'x + 1' is not a finite real number"]
    assert q["sympy"] == {"expr": "x + 1", "verified": False}


def test_short_answer_with_a_comma_decimal_is_compared_as_a_number():
    assert check_answer(_q("short_answer", answer="-1,5", sympy={"expr": "-Rational(3, 2)"})) == []


@pytest.mark.parametrize("expr", ["__import__('os')", "().__class__"])
def test_short_answer_with_a_dunder_expr_is_rejected_not_run(expr):
    errors = check_answer(_q("short_answer", sympy={"expr": expr}))

    assert errors == ["sympy.expr unverifiable: expression contains '__'"]


# --- multiple choice (checked only when the correct option is a plain number) ---------------------------------

@pytest.mark.parametrize("answer, expr", [("A", "-Rational(3, 2)"), ("C", "Rational(3, 2)"), ("D", "1 - 1")])
def test_multiple_choice_plain_number_option_is_checked(answer, expr):
    q = _q("multiple_choice", **NUMERIC_MC, answer=answer, sympy={"expr": expr})

    assert check_answer(q) == []
    assert q["sympy"] == {"expr": expr, "verified": True}


def test_multiple_choice_plain_number_option_sympy_disagrees_is_rejected():
    q = _q("multiple_choice", **NUMERIC_MC, answer="B", sympy={"expr": "1 + 2"})

    assert check_answer(q) == ["answer 2 but SymPy gives 3 for '1 + 2'"]


def test_multiple_choice_non_numeric_option_is_left_unverified_not_rejected():
    q = _q("multiple_choice", sympy={"expr": "2"})

    assert check_answer(q) == []
    assert q["sympy"] == {"expr": "2", "verified": False}


def test_multiple_choice_null_sympy_expr_is_dropped():
    q = _q("multiple_choice")

    assert check_answer(q) == []
    assert "sympy" not in q


def test_multiple_choice_unverifiable_expr_is_kept_unverified():
    q = _q("multiple_choice", **NUMERIC_MC, answer="B", sympy={"expr": "x"})

    assert check_answer(q) == []  # only short answers are rejected for an unreadable expr
    assert q["sympy"] == {"expr": "x", "verified": False}


@pytest.mark.parametrize("option", ["$ 2 $", "2", " $2$ "])
def test_dollar_signs_and_spaces_around_a_number_are_ignored(option):
    q = _q("multiple_choice", options={"A": option, "B": "1", "C": "3", "D": "4"}, answer="A", sympy={"expr": "1 + 1"})

    check_answer(q)

    assert q["sympy"]["verified"] is True


@pytest.mark.parametrize("option", ["$\\frac{1}{2}$", "1/2", "$2\\sqrt{3}$", "2x", "Đáp án khác"])
def test_options_that_are_not_plain_numbers_are_not_checked(option):
    q = _q("multiple_choice", options={"A": option, "B": "1", "C": "3", "D": "4"}, answer="A", sympy={"expr": "5"})

    assert check_answer(q) == [] and q["sympy"]["verified"] is False


def test_an_answer_letter_without_an_option_is_not_checked():
    q = _q("multiple_choice", options={"A": "1", "B": "2", "C": "3"}, answer="D", sympy={"expr": "4"})

    assert check_answer(q) == [] and q["sympy"]["verified"] is False


# --- other types -----------------------------------------------------------------------------------------------

def test_true_false_is_never_checked():
    q = _q("true_false") | {"sympy": {"expr": "1"}}

    assert check_answer(q) == []
    assert q["sympy"] == {"expr": "1"}  # untouched


@pytest.mark.parametrize("qtype", [None, "essay"])
def test_unknown_types_are_left_to_validate(qtype):
    q = _q("short_answer", type=qtype, sympy={"expr": "999"})

    assert check_answer(q) == []


def test_retrieved_ids_are_ignored():
    assert check_answer(_q("short_answer"), {"unrelated"}) == check_answer(_q("short_answer"), None) == []


# --- BUG-003: the expression must compute the answer, not restate it -------------------------------------------

@pytest.mark.parametrize("answer, expr", [("21", "21"), ("40", "40"), ("-1,5", "-1.5"), ("0,25", " 0,25 "), ("7", "+7")])
def test_BUG_003_short_answer_whose_expr_only_restates_the_answer_is_rejected(answer, expr):
    """Q20 / Q19 of exam e81f6617: expr "21" / "40" made verified: true although the answers were wrong."""
    q = _q("short_answer", answer=answer, sympy={"expr": expr})

    assert check_answer(q) == ["sympy.expr only restates the answer; it must compute it from the question's data"]
    assert q["sympy"] == {"expr": expr, "verified": False}


@pytest.mark.parametrize("expr", ["Rational(20, 3)", "2*pi", "Integral(x**2, (x, 0, 3))", "sqrt(49)", "3 + 4"])
def test_BUG_003_an_expression_that_computes_the_answer_is_still_verified(expr):
    from sympy import N, sympify

    answer = format(round(float(N(sympify(expr).doit())), 2), "g").replace(".", ",")
    q = _q("short_answer", answer=answer, sympy={"expr": expr})

    assert check_answer(q) == []
    assert q["sympy"]["verified"] is True


def test_BUG_003_multiple_choice_with_a_bare_number_expr_is_left_unverified_not_rejected():
    q = _q("multiple_choice", **NUMERIC_MC, answer="B", sympy={"expr": "2"})

    assert check_answer(q) == []
    assert q["sympy"] == {"expr": "2", "verified": False}
