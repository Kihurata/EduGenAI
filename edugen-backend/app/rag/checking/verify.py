"""Tóm tắt: kiểm chứng đáp số bằng SymPy. `verify` (T-014, TC-015): tính biểu thức, làm tròn theo số chữ số thập phân của đáp số rồi so sánh; biểu thức hỏng thì trả "unverifiable", không ném lỗi. `check_answer` (T-031): bước kiểm tra trong pipeline: câu trả lời ngắn thiếu biểu thức, lệch hoặc không tính được thì bị loại; trắc nghiệm có phương án đúng là số mà lệch thì bị loại. Biểu thức chỉ là một con số (chép lại đáp án) không chứng minh gì: câu trả lời ngắn bị loại, trắc nghiệm để chưa kiểm (BUG-003)."""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

import sympy
from sympy.parsing.sympy_parser import parse_expr

from app.rag.dto import Question, Verification

_NUMBER = re.compile(r"-?\d+([.,]\d+)?")
# BUG-003: an expr that is only a number restates the answer instead of computing it, so it proves nothing.
_BARE_NUMBER = re.compile(r"\s*[-+]?\d+([.,]\d+)?\s*")
RESTATED = "sympy.expr only restates the answer; it must compute it from the question's data"
# Names an expression may use: SymPy's public API only. parse_expr's default namespace also holds Python built-ins
# (open, eval, exec, ...), which let LLM- or teacher-written text run code; "__builtins__": {} removes them.
_NAMESPACE = {name: getattr(sympy, name) for name in sympy.__all__} | {"__builtins__": {}}
# The LLM also writes Python's comb and round. round passes the value through: verify() rounds half up to the
# answer's places, while Python/SymPy round half to even.
_NAMESPACE |= {"comb": sympy.binomial, "round": lambda x, ndigits=None: x}


def _unverifiable(answer, reason):
    return Verification("unverifiable", answer, None, reason)


def verify(expr, answer) -> Verification:
    try:
        expected = Decimal(answer.replace(",", "."))
    except (AttributeError, InvalidOperation):
        return _unverifiable(answer, f"answer {answer!r} is not a number")
    if "__" in expr:  # parse_expr evals its input: block dunder escapes from LLM-written text
        return _unverifiable(answer, "expression contains '__'")
    if "'" in expr or '"' in expr:  # SymPy re-parses string arguments with Python built-ins in scope
        return _unverifiable(answer, "expression contains a string")
    try:
        number = parse_expr(expr, global_dict=dict(_NAMESPACE)).doit().evalf(50)
    except Exception as e:  # noqa: BLE001 -- SymPy raises many types on bad input; never crash the pipeline
        return _unverifiable(answer, f"cannot evaluate: {type(e).__name__}")
    if not (number.is_Number and number.is_finite):  # free symbols, complex, oo, zoo, nan
        return _unverifiable(answer, f"{expr!r} is not a finite real number")
    try:
        with localcontext(prec=100):  # default 28 digits can't quantize big (mismatching) values
            # Round half up (school rule) to the answer's decimal places; + 0 turns -0 into 0.
            value = Decimal(str(number)).quantize(Decimal(1).scaleb(expected.as_tuple().exponent), ROUND_HALF_UP) + 0
    except InvalidOperation:
        return _unverifiable(answer, f"value of {expr!r} is too large to round")
    status = "verified" if value == expected else "mismatch"
    return Verification(status, answer, format(value, "f").replace(".", ","))


def restates_answer(expr) -> bool:
    """BUG-003: the expression is only a number, so it restates the answer instead of computing it."""
    return isinstance(expr, str) and _BARE_NUMBER.fullmatch(expr) is not None


def check_answer(q: Question, retrieved_ids=None) -> list[str]:
    """Sets q["sympy"] = {"expr", "verified"} (dropped when there is no expr); -> errors."""
    kind = q.get("type")
    if kind not in ("short_answer", "multiple_choice"):
        return []
    expr = (q.get("sympy") or {}).get("expr")
    if not isinstance(expr, str) or not expr.strip():
        q.pop("sympy", None)
        return ["no sympy.expr"] if kind == "short_answer" else []  # F-04: every short answer is verified
    if restates_answer(expr):
        q["sympy"] = {"expr": expr, "verified": False}
        return [RESTATED] if kind == "short_answer" else []
    if kind == "short_answer":
        answer = q.get("answer")
    else:
        answer = str((q.get("options") or {}).get(q.get("answer"), "")).replace("$", "").replace(" ", "")
        if not _NUMBER.fullmatch(answer):  # only a plain-number option can be checked
            q["sympy"] = {"expr": expr, "verified": False}
            return []
    result = verify(expr, answer)
    q["sympy"] = {"expr": expr, "verified": result.status == "verified"}
    if result.status == "mismatch":
        return [f"answer {answer} but SymPy gives {result.value} for {expr!r}"]
    if result.status == "unverifiable" and kind == "short_answer":
        return [f"sympy.expr unverifiable: {result.reason}"]
    return []
