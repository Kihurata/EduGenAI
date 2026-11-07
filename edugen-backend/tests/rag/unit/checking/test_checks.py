"""Tóm tắt: unit test danh sách các bước kiểm tra (CHECKS): định dạng chạy trước SymPy, lỗi của mọi bước được gộp theo thứ tự, câu hợp lệ không có lỗi, thêm một bước kiểm tra không cần sửa pipeline."""

import copy

from app.rag import checking
from app.rag.checking import CHECKS, check
from app.rag.checking.toxic import check_toxic
from app.rag.checking.validate import validate
from app.rag.checking.verify import check_answer
from tests.rag.support import LLM_OUTPUT

RETRIEVED = {"t1", "t2"}


def _q(qtype, **over):
    return copy.deepcopy(LLM_OUTPUT[qtype]) | {"type": qtype, "level": "Biết", "topic": "t"} | over


def test_checks_run_format_first_then_sympy():
    assert CHECKS == (validate, check_answer, check_toxic)


def test_a_valid_question_passes_every_check():
    for qtype in LLM_OUTPUT:
        assert check(_q(qtype), RETRIEVED) == [], qtype


def test_errors_of_every_check_are_joined_in_order():
    q = _q("short_answer", source_chunk_ids=["x"], sympy={"expr": "1 + 2"})

    assert check(q, RETRIEVED) == ["cites chunk x that was not retrieved", "answer 2 but SymPy gives 3 for '1 + 2'"]


def test_sympy_still_runs_when_the_format_is_wrong():
    q = _q("short_answer", answer="12345", sympy={"expr": "12344 + 1"})

    errors = check(q, RETRIEVED)

    assert errors == ["short_answer '12345' does not fit the 4 answer-sheet boxes"]
    assert q["sympy"] == {"expr": "12344 + 1", "verified": True}


def test_teacher_edits_are_checked_without_retrieval():
    assert check(_q("multiple_choice", source_chunk_ids=["anything"]), None) == []


def test_a_new_check_is_added_without_touching_the_pipeline(monkeypatch):
    monkeypatch.setattr(checking, "CHECKS", CHECKS + (lambda q, ids: ["stem too short"] if len(q["stem"]) < 5 else [],))

    assert checking.check(_q("multiple_choice", stem="?"), RETRIEVED) == ["stem too short"]
