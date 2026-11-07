"""Job nền sinh đề (gọi RAG từng ô của ma trận đã xác nhận) và xuất DOCX."""

import logging
import uuid
from collections import Counter

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import LLMError
from app.domain.cell import Cell
from app.domain.exam_document import ExamInfo, build_blocks
from app.domain.exam_variant import make_variant, variant_seed
from app.domain.generation import QuestionGenerator, generate_all
from app.domain.matrix_json import exam_kind_of
from app.models import (
    Exam,
    ExamCellRun,
    ExamExport,
    ExamMatrix,
    ExamQuestion,
    MatrixCell,
    School,
)
from app.models.enums import CellRunStatus, ExamStatus, ExportVariant, Level
from app.services.docx_export import to_docx
from app.services.storage import LocalStorage

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
log = logging.getLogger("edugen.exam_jobs")
GENERIC_ERROR = "Lỗi hệ thống khi sinh đề, vui lòng thử lại hoặc báo quản trị viên."


class _CellGuard:
    """Bọc RAG: lỗi bất ngờ ở một ô chỉ làm ô đó lỗi (LLMError), các ô khác vẫn chạy tiếp."""

    def __init__(self, rag: QuestionGenerator) -> None:
        self._rag = rag

    def generate(self, cell: Cell):
        try:
            return self._rag.generate(cell)
        except LLMError:
            raise
        except Exception:
            log.exception("sinh ô %s lỗi", cell.id)
            raise LLMError(GENERIC_ERROR) from None

    def validate(self, question, cell):
        return self._rag.validate(question, cell)


def cell_of(matrix: ExamMatrix, row: MatrixCell, count: int | None = None) -> Cell:
    """Ô ma trận trong DB → ô gửi RAG; `count` để sinh ít hơn số câu của ô (sinh lại, bù câu)."""
    return Cell(
        id=row.sort_order, subject=matrix.subject.code, grade=matrix.grade, topic=row.topic,
        content_unit=row.content_unit, type=row.question_type, level=row.level,
        count=row.question_count if count is None else count,
        statement_levels=tuple(Level(v) for v in row.statement_levels) if row.statement_levels else None,
        competency_codes=tuple(row.competency_codes or ()), school_id=str(matrix.school_id),
        teacher_id=str(matrix.owner_id),  # GV của ma trận: thấy đề mẫu GV đó tự tải
        exam_kind=exam_kind_of(matrix.name),
        statement_units=tuple(row.statement_units) if row.statement_units else None,
    )  # fmt: skip


def settle(exam: Exam) -> None:
    """Đánh lại số thứ tự câu theo thứ tự ô, đếm lại câu từng ô và tính trạng thái đề.

    Gọi sau mỗi lần sinh, sửa, xoá. Ô thiếu câu mà lần gọi RAG gần nhất lỗi thì giữ `error`.
    """
    rows = {c.id: c for c in exam.matrix.cells}
    questions = sorted(exam.questions, key=lambda q: (rows[q.matrix_cell_id].sort_order, q.position))
    for position, question in enumerate(questions, start=1):
        question.position = position
    counts = Counter(q.matrix_cell_id for q in questions)
    for run in exam.cell_runs:
        run.valid_count = counts[run.matrix_cell_id]
        if run.valid_count >= rows[run.matrix_cell_id].question_count:
            run.status = CellRunStatus.complete
        else:
            run.status = CellRunStatus.error if run.error_message else CellRunStatus.short
    if not questions:
        exam.status = ExamStatus.failed
    elif all(r.status is CellRunStatus.complete for r in exam.cell_runs):
        exam.status = ExamStatus.generated
    else:
        exam.status = ExamStatus.incomplete


def run_exam_generation(session_factory: sessionmaker, exam_id: uuid.UUID, rag: QuestionGenerator) -> None:
    with session_factory() as session:
        try:
            exam = session.get(Exam, exam_id)
            if exam is None:
                return
            matrix = exam.matrix
            rows = {c.sort_order: c for c in matrix.cells}
            cells = [cell_of(matrix, c) for c in matrix.cells]

            def progress(done: int, total: int) -> None:
                exam.cells_done = done
                session.commit()  # frontend hỏi lại thấy tiến độ

            runs = generate_all(cells, _CellGuard(rag), on_progress=progress)
            position = 0
            for run in runs:
                row = rows[run.cell.id]
                exam.cell_runs.append(ExamCellRun(
                    matrix_cell_id=row.id, status=run.status, valid_count=len(run.questions),
                    rejected_count=run.rejected_count, error_message=run.error,
                ))  # fmt: skip
                for question in run.questions:
                    position += 1
                    exam.questions.append(
                        ExamQuestion(matrix_cell_id=row.id, position=position, content=question)
                    )
            settle(exam)
            session.commit()
        except Exception:
            session.rollback()
            log.exception("sinh đề lỗi")
            _mark_generation_failed(session_factory, exam_id, GENERIC_ERROR)


def _mark_generation_failed(session_factory: sessionmaker, exam_id: uuid.UUID, message: str) -> None:
    try:
        with session_factory() as session:
            exam = session.get(Exam, exam_id)
            if exam is None:
                return
            completed = {run.matrix_cell_id for run in exam.cell_runs}
            for row in exam.matrix.cells:
                if row.id not in completed:
                    exam.cell_runs.append(ExamCellRun(
                        matrix_cell_id=row.id, status=CellRunStatus.error,
                        valid_count=0, rejected_count=0, error_message=message,
                    ))  # fmt: skip
            exam.status = ExamStatus.incomplete if exam.questions else ExamStatus.failed
            session.commit()
    except Exception:
        log.exception("không ghi được trạng thái lỗi cho đề %s", exam_id)


def variant_questions(exam: Exam, code: str) -> list[dict]:
    """Câu của đề theo mã đề (đã xáo). Xuất file và xem trước dùng chung hàm này để luôn khớp nhau."""
    return make_variant([q.content for q in exam.questions], variant_seed(exam.id, code))


def export_exam(
    session: Session, storage: LocalStorage, exam: Exam, variant: ExportVariant, code: str | None = None
) -> tuple[bytes, str]:
    """Dựng DOCX, lưu vào storage và ghi exam_exports; trả (nội dung, tên file).

    `code` là mã đề: câu và phương án được xáo theo seed của (đề, mã đề) và mã in trên đề; không có
    thì xuất bản gốc. Đề đã duyệt không sửa được nên cùng mã luôn ra cùng thứ tự.
    """
    matrix = exam.matrix
    info = ExamInfo(
        school_name=session.get(School, exam.school_id).name, title=exam.title,
        subject_name=matrix.subject.name, grade=matrix.grade, duration_minutes=exam.duration_minutes,
        code=code,
    )  # fmt: skip
    cells = [cell_of(matrix, row) for row in matrix.cells]
    questions = variant_questions(exam, code) if code else [q.content for q in exam.questions]
    data = to_docx(build_blocks(info, questions, variant, cells))
    key = f"exports/{exam.id}/{uuid.uuid4()}-{variant.value}{f'-{code}' if code else ''}.docx"
    storage.save(key, data)
    session.add(ExamExport(exam_id=exam.id, variant=variant, storage_key=key))
    session.commit()
    suffix = "GV" if variant is ExportVariant.teacher else "HS"
    return data, f"{exam.title} - {suffix}{f' - Mã đề {code}' if code else ''}.docx"
