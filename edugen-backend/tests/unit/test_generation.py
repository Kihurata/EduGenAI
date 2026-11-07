"""Workflow ④ – Sinh câu cho từng ô.

Đầu ra mong muốn:
- Gọi generate(cell) đúng MỘT lần mỗi ô, nhận (valid, rejected).
- Câu RAG trả về được BE kiểm cấu trúc lại; câu sai cấu trúc tính là bị loại.
- Đủ câu → ô complete. Thiếu câu → ô short, không tự gọi bù. LLMError → ô error,
  các ô khác vẫn chạy tiếp.
- Báo tiến độ sau mỗi ô để giao diện hỏi lại khi chạy nền.
"""

from dataclasses import replace

import pytest

from app.core.errors import LLMError
from app.domain.cell import Cell
from app.domain.generation import generate_all
from app.models.enums import CellRunStatus, Level, QuestionType


def cell(id_: int, count: int = 2) -> Cell:
    return Cell(id_, "toan", 12, "Ứng dụng đạo hàm", "Cực trị", QuestionType.multiple_choice, Level.biet, count)


def raw(stem: str) -> dict:
    return {
        "dang": "nhieu_lua_chon", "muc_do": "Biet", "de_bai": stem,
        "phuong_an": ["1", "2", "3", "4"], "dap_an": "A", "loi_giai": "Vì vậy.",
    }  # fmt: skip


class FakeRag:
    """valid_counts[cell.id] = số câu hợp lệ trả về; errors[cell.id] = exception ném ra."""

    def __init__(self, valid_counts=None, errors=None, rejected=0, malformed=0):
        self.valid_counts = valid_counts or {}
        self.errors = errors or {}
        self.rejected = rejected
        self.malformed = malformed
        self.calls: list[Cell] = []

    def generate(self, c: Cell):
        self.calls.append(c)
        if c.id in self.errors:
            raise self.errors[c.id]
        n = self.valid_counts.get(c.id, c.count)
        valid = [raw(f"ô {c.id} câu {i}") for i in range(n)]
        valid += [{"dang": "nhieu_lua_chon"}] * self.malformed
        return valid, [{"loi": "x"}] * self.rejected


def test_cell_with_enough_questions_is_complete():
    [run] = generate_all([cell(1, 2)], FakeRag(rejected=1))
    assert run.status == CellRunStatus.complete
    assert [q["stem"] for q in run.questions] == ["ô 1 câu 0", "ô 1 câu 1"]
    assert run.questions[0]["type"] == "multiple_choice"
    assert run.rejected_count == 1
    assert run.error is None


def test_cell_short_of_questions_is_marked_short_without_retry():
    rag = FakeRag(valid_counts={1: 1})
    [run] = generate_all([cell(1, 3)], rag)
    assert run.status == CellRunStatus.short
    assert len(run.questions) == 1
    assert len(rag.calls) == 1  # không tự bù


def test_malformed_questions_count_as_rejected():
    [run] = generate_all([cell(1, 2)], FakeRag(valid_counts={1: 1}, rejected=1, malformed=2))
    assert run.status == CellRunStatus.short
    assert len(run.questions) == 1
    assert run.rejected_count == 3


def test_extra_questions_beyond_count_are_dropped():
    [run] = generate_all([cell(1, 2)], FakeRag(valid_counts={1: 5}))
    assert run.status == CellRunStatus.complete
    assert len(run.questions) == 2


def test_llm_error_marks_cell_and_other_cells_continue():
    rag = FakeRag(errors={2: LLMError("model quá tải")})
    runs = generate_all([cell(1), cell(2), cell(3)], rag)
    assert [r.status for r in runs] == [CellRunStatus.complete, CellRunStatus.error, CellRunStatus.complete]
    assert runs[1].error == "model quá tải"
    assert runs[1].questions == []
    assert [c.id for c in rag.calls] == [1, 2, 3]


def test_programming_errors_are_not_swallowed():
    with pytest.raises(KeyError):
        generate_all([cell(1)], FakeRag(errors={1: KeyError("bug")}))


def test_each_cell_is_called_exactly_once_with_the_cell_itself():
    cells = [cell(1), cell(2)]
    rag = FakeRag()
    generate_all(cells, rag)
    assert [replace(c, previous_stems=()) for c in rag.calls] == cells  # BUG-005 adds the earlier stems


def test_progress_is_reported_after_each_cell():
    progress = []
    generate_all([cell(1), cell(2), cell(3)], FakeRag(errors={2: LLMError("x")}), on_progress=lambda d, t: progress.append((d, t)))
    assert progress == [(1, 3), (2, 3), (3, 3)]


# ----- BUG-005: no repeated question within one exam -----


def test_BUG_005_later_cells_see_the_stems_of_earlier_valid_questions():
    rag = FakeRag()

    generate_all([cell(1), cell(2), cell(3, count=1)], rag)

    assert [c.previous_stems for c in rag.calls] == [
        (), ("ô 1 câu 0", "ô 1 câu 1"), ("ô 1 câu 0", "ô 1 câu 1", "ô 2 câu 0", "ô 2 câu 1")]

