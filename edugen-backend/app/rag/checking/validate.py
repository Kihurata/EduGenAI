"""Tóm tắt: kiểm tra câu hỏi sinh ra (T-009). Trả về danh sách lý do lỗi (rỗng = hợp lệ): trích dẫn phải nằm trong các đoạn đã truy xuất, trắc nghiệm đủ A–D, Đ/S đủ 4 ý a–d, đáp án Phần III vừa 4 ô của phiếu. Mỗi dạng câu có một hàm luật riêng."""

import re

# Answer sheet Part III: 4 boxes, each a digit, "-" or the decimal comma (CV 1239/BGDĐT-QLCL).
_SHORT_ANSWER = re.compile(r"-?[0-9]+(,[0-9]+)?")


def validate(question, retrieved_ids):
    """-> error messages, shown to the teacher as-is; retrieved_ids None = teacher edit (no retrieval to check)."""
    rules = _RULES_BY_TYPE.get(question.get("type"))
    type_errors = rules(question) if rules else [f"unknown question type {question.get('type')!r}"]
    return _citation_errors(question, retrieved_ids) + _table_errors(question) + type_errors


def _citation_errors(question, retrieved_ids):
    cited = question.get("source_chunk_ids") or []
    errors = [] if cited else ["no source_chunk_ids"]
    if retrieved_ids is not None:
        errors += [f"cites chunk {c} that was not retrieved" for c in cited if c not in retrieved_ids]
    return errors


def _table_errors(question):
    """Rows of different lengths shift columns in the exam file (the variation table's y' / y rows), so ask again."""
    rows = question.get("table")
    if rows and len({len(r) for r in rows}) > 1:
        return [f"table rows must all have the same number of cells, got {[len(r) for r in rows]}"]
    return []


def _multiple_choice_errors(question):
    errors = []
    if sorted(question.get("options") or {}) != list("ABCD"):
        errors.append("multiple_choice needs exactly options A, B, C, D")
    if question.get("answer") not in ("A", "B", "C", "D"):
        errors.append(f"multiple_choice answer {question.get('answer')!r} is not A–D")
    return errors


def _true_false_errors(question):
    statements = question.get("statements") or []
    errors = []
    if [s.get("label") for s in statements] != list("abcd"):
        errors.append("true_false needs exactly 4 statements a, b, c, d")
    if not all(isinstance(s.get("answer"), bool) for s in statements):
        errors.append("true_false statement answers must be true/false")
    return errors


def _short_answer_errors(question):
    answer = question.get("answer")
    if not isinstance(answer, str) or not _SHORT_ANSWER.fullmatch(answer):
        return [f"short_answer {answer!r} is not a number written with digits, '-' and ','"]
    if len(answer) > 4:
        return [f"short_answer {answer!r} does not fit the 4 answer-sheet boxes"]
    return []


_RULES_BY_TYPE = {
    "multiple_choice": _multiple_choice_errors,
    "true_false": _true_false_errors,
    "short_answer": _short_answer_errors,
}
