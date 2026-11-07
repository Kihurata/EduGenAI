"""Tóm tắt: bước kiểm tra câu sinh ra: danh sách các bước kiểm tra chạy lần lượt trên mỗi câu; lỗi của mọi bước được gộp lại.

A check is `check(question, retrieved_ids) -> [error]`; it may set fields on the question (check_answer sets
`sympy`). Add a check by appending it to CHECKS; the pipeline does not change.
"""

from collections.abc import Callable

from app.rag.checking.toxic import check_toxic
from app.rag.checking.validate import validate
from app.rag.checking.verify import check_answer
from app.rag.dto import Question

Check = Callable[[Question, set[str] | None], list[str]]
CHECKS: tuple[Check, ...] = (validate, check_answer, check_toxic)  # order kept: format first, then SymPy


def check(question: Question, retrieved_ids: set[str] | None) -> list[str]:
    return [error for c in CHECKS for error in c(question, retrieved_ids)]
