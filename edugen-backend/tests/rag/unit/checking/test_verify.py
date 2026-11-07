"""Tóm tắt: unit test kiểm chứng đáp số bằng SymPy (T-014, TC-015): khớp sau khi làm tròn thì đạt, lệch thì báo giá trị SymPy, biểu thức hỏng thì "unverifiable" và không bao giờ ném lỗi; thêm làm tròn nửa lên, số âm, hằng số, số quá lớn, và test áp lực với hàng trăm phân số ngẫu nhiên."""

import random
from decimal import ROUND_HALF_UP, Decimal

import pytest

from app.rag.checking.verify import verify
from app.rag.dto import Verification

# --- existing behaviour (TC-015) -------------------------------------------------------------------------------

@pytest.mark.parametrize("expr, answer, status, value", [
    ("-3/2", "-1,5", "verified", "-1,5"),
    ("1/3", "0,33", "verified", "0,33"),
    ("Integral(x**2, (x, 0, 3))", "9", "verified", "9"),
    ("2+2", "5", "mismatch", "4"),
    ("sqrt((", "1", "unverifiable", None),
    ("x+1", "1", "unverifiable", None),
])
def test_TC_015_short_answer_matches_sympy(expr, answer, status, value):
    result = verify(expr, answer)
    assert (result.status, result.answer, result.value) == (status, answer, value)


@pytest.mark.parametrize("expr, answer", [
    ("1/8", "0,13"),      # tie rounds half up, as taught in school
    ("-1/1000", "0"),     # rounds to 0, not "-0"
    ("sqrt(2)", "1,41"),
    ("5/2", "2,50"),      # trailing zero still compares as a number
])
def test_rounding_and_number_comparison(expr, answer):
    assert verify(expr, answer).status == "verified"


def test_negative_zero_value_is_written_as_zero():
    assert verify("-1/1000", "1").value == "0"


@pytest.mark.parametrize("expr, answer", [
    ("1/0", "1"),              # complex infinity
    ("oo", "1"),
    ("sqrt(-1)", "1"),         # not real
    ("2", "abc"),              # answer is not a number
    ("__import__('os')", "1"),
    ("", "1"),
])
def test_unverifiable_inputs_never_raise(expr, answer):
    assert verify(expr, answer).status == "unverifiable"


# --- result shape ----------------------------------------------------------------------------------------------

def test_result_is_a_verification_dto():
    assert verify("2", "2") == Verification("verified", "2", "2", None)


def test_a_mismatch_reports_the_sympy_value_rounded_like_the_answer():
    assert verify("Rational(7, 3)", "2,5") == Verification("mismatch", "2,5", "2,3", None)


@pytest.mark.parametrize("expr, answer, reason", [
    ("2", "abc", "answer 'abc' is not a number"),
    ("().__class__", "1", "expression contains '__'"),
    ("sqrt((", "1", "cannot evaluate: "),
    ("x", "1", "'x' is not a finite real number"),
    ("10**200", "1", "too large to round"),
])
def test_unverifiable_results_say_why(expr, answer, reason):
    result = verify(expr, answer)

    assert result.status == "unverifiable" and result.value is None and reason in result.reason


# --- numbers and rounding --------------------------------------------------------------------------------------

@pytest.mark.parametrize("expr, answer", [
    ("pi", "3,14"), ("E", "2,72"), ("sqrt(3)", "1,73"), ("log(E**2)", "2"), ("exp(0)", "1"),
    ("sin(pi/6)", "0,5"), ("cos(0)", "1"), ("factorial(5)", "120"), ("binomial(10, 3)", "120"),
    ("diff(x**3, x).subs(x, 2)", "12"), ("Integral(1/x, (x, 1, E))", "1"), ("Rational(1, 4)", "0,25"),
])
def test_common_school_expressions(expr, answer):
    assert verify(expr, answer).status == "verified", expr


@pytest.mark.parametrize("expr, answer", [("-1/8", "-0,13"), ("-5/2", "-3"), ("-0,0", "0")])
def test_negative_ties_round_away_from_zero(expr, answer):
    assert verify(expr.replace(",", "."), answer).status == "verified"


@pytest.mark.parametrize("expr, answer", [("2", "2,0"), ("2", "2,00"), ("Rational(1,2)", "0,50")])
def test_more_decimals_in_the_answer_still_match(expr, answer):
    assert verify(expr, answer).status == "verified"


def test_a_dot_decimal_answer_is_read_as_a_number():
    assert verify("3/2", "1.5").status == "verified"  # validate() rejects the dot; verify only compares values


@pytest.mark.parametrize("answer", [None, 15, ""])
def test_answers_that_are_not_text_numbers_are_unverifiable(answer):
    assert verify("15", answer).status == "unverifiable"


def test_whitespace_around_the_expression_is_fine():
    assert verify("  2 + 3  ", "5").status == "verified"


@pytest.mark.parametrize("expr", ["I", "sqrt(-4)", "zoo", "nan", "-oo", "x*y", "Symbol('t')"])
def test_non_real_or_symbolic_values_are_unverifiable(expr):
    assert verify(expr, "1").status == "unverifiable"


@pytest.mark.parametrize("expr", ["__import__('os').system('true')", "().__class__.__bases__",
                                  "x.__class__", "Rational.__init__"])
def test_dunder_access_is_never_evaluated(expr):
    assert verify(expr, "1").reason == "expression contains '__'"


# --- stress: random fractions against a Decimal reference ------------------------------------------------------

@pytest.mark.parametrize("seed", range(4))
def test_random_fractions_verify_against_half_up_rounding(seed):
    rng = random.Random(seed)
    for _ in range(60):
        p, q, places = rng.randint(-999, 999), rng.randint(1, 97), rng.choice([0, 1, 2])
        exact = Decimal(p) / Decimal(q)
        rounded = exact.quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP) + 0
        answer = format(rounded, "f").replace(".", ",")

        assert verify(f"Rational({p}, {q})", answer).status == "verified", (p, q, answer)
        off = format(rounded + Decimal(1).scaleb(-places), "f").replace(".", ",")
        assert verify(f"Rational({p}, {q})", off).status == "mismatch", (p, q, off)


# --- the expression evaluator has no Python built-ins (T-014 risk) ---------------------------------------------

def test_an_expression_cannot_open_files(tmp_path):
    target = tmp_path / "written-by-expr"

    result = verify(f"open({str(target)!r}, 'w')", "1")

    assert not target.exists() and result.status == "unverifiable"


def test_an_expression_cannot_run_code_through_exec(tmp_path):
    target = tmp_path / "written-by-exec"

    verify(f"exec({'open(' + repr(str(target)) + ', ' + repr('w') + ')'!r})", "1")

    assert not target.exists()


# --- names the LLM writes from Python's math module (T-036 runs: comb, round were unverifiable) ------------------

@pytest.mark.parametrize("expr, answer", [
    ("comb(7, 4)*comb(6, 1) + comb(7, 3)*comb(6, 2)", "735"),
    ("comb(11, 4) - comb(6, 4) - comb(5, 4)", "310"),
    ("round(1 - (comb(6, 3) + comb(3, 1) * comb(6, 2)) / comb(12, 3), 2)", "0,70"),
])
def test_comb_and_round_from_generated_answers_verify(expr, answer):
    assert verify(expr, answer).status == "verified", expr


def test_round_does_not_override_half_up_rounding():
    assert verify("round(Rational(5, 2))", "3").status == "verified"  # Python/SymPy round half to even would give 2
