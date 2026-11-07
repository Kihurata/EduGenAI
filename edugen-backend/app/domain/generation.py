"""Workflow ④: sinh câu cho từng ô.

Mỗi ô gọi RAG đúng một lần; câu RAG trả về được kiểm lại cấu trúc (domain/question.py),
câu sai cấu trúc tính là bị loại. Câu có `figure_spec` được vẽ `figure_svg`; spec hỏng chỉ mất hình, câu không bị loại. Ô thiếu câu không được tự bù (giáo viên quyết định ở bước
duyệt); ô lỗi LLM không chặn các ô khác. Lỗi lập trình (không phải LLMError) vẫn nổi lên.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Protocol

from app.core.errors import LLMError
from app.domain.cell import Cell
from app.domain.figure import with_figure
from app.domain.question import Question, split_questions
from app.models.enums import CellRunStatus


class QuestionGenerator(Protocol):
    """Hợp đồng với RAG: generate(cell) → (valid, rejected); validate(question, cell) → lỗi."""

    def generate(self, cell: Cell) -> tuple[list[Question], list[Question]]: ...

    def validate(self, question: Question, cell: Cell | None) -> list[str]: ...


@dataclass
class CellRun:
    cell: Cell
    status: CellRunStatus
    questions: list[Question] = field(default_factory=list)
    rejected_count: int = 0
    error: str | None = None


def generate_cell(cell: Cell, rag: QuestionGenerator) -> CellRun:
    try:
        valid, rejected = rag.generate(cell)
    except LLMError as exc:
        return CellRun(cell, CellRunStatus.error, error=str(exc))
    valid, malformed = split_questions(valid, cell)
    valid = [with_figure(q) for q in valid[: cell.count]]  # RAG trả dư thì bỏ phần dư; chỉ vẽ hình câu được giữ
    status = CellRunStatus.complete if len(valid) == cell.count else CellRunStatus.short
    return CellRun(cell, status, valid, len(rejected) + len(malformed))


def generate_all(
    cells: Sequence[Cell],
    rag: QuestionGenerator,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[CellRun]:
    """Sinh lần lượt mọi ô; on_progress(số ô xong, tổng số ô) cho job chạy nền."""
    runs, stems = [], []
    for done, cell in enumerate(cells, start=1):
        run = generate_cell(replace(cell, previous_stems=tuple(stems)), rag)  # BUG-005: no repeats across cells
        stems += [q["stem"] for q in run.questions]
        runs.append(run)
        if on_progress:
            on_progress(done, len(cells))
    return runs
