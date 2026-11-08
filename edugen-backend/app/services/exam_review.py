"""Giáo viên duyệt đề (F-05): sửa, xoá, sinh lại từng câu, bù ô thiếu, duyệt.

Câu GV sửa đi qua đúng bộ kiểm cấu trúc dùng cho câu RAG trả (domain/question.py), rồi RAG
/validate. Sinh lại và bù câu chạy nền như sinh đề: đề chuyển `generating` trong lúc chờ.
"""

import logging
import uuid
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import sessionmaker

from app.domain.exam_structure import PART_OF_TYPE
from app.domain.figure import with_figure
from app.domain.generation import QuestionGenerator, generate_cell
from app.domain.question import parse_question, to_rag
from app.models import Exam, ExamQuestion, MatrixCell
from app.rag.checking.verify import restates_answer
from app.services.exam_jobs import GENERIC_ERROR, cell_of, settle

FILL_ROUNDS = 3
NO_VALID_QUESTION = "RAG không trả được câu hợp lệ"
log = logging.getLogger("edugen.exam_review")


def edit_question(question: ExamQuestion, content: dict[str, Any], rag: QuestionGenerator) -> list[str]:
    """Kiểm rồi lưu câu GV sửa; trả lỗi (câu cũ giữ nguyên) hoặc []. LLMError nổi lên cho API.

    Trích dẫn giữ như cũ (GV không sửa nguồn); kết quả SymPy cũ bỏ vì không còn đúng với câu mới.
    """
    cell = cell_of(question.matrix_cell.matrix, question.matrix_cell)
    raw = to_rag(content | {"citations": question.content.get("citations") or [], "check": None})
    normalized, errors = parse_question(raw, cell)
    if errors:
        return errors
    errors = rag.validate(raw, cell)
    if errors:
        return errors
    if question.original is None:
        question.original = question.content
    question.content = with_figure(normalized)  # SVG vẽ lại từ spec mới; SVG máy khách gửi lên không được tin
    return []


def missing_count(exam: Exam, row: MatrixCell) -> int:
    return row.question_count - sum(q.matrix_cell_id == row.id for q in exam.questions)


def approval_problems(exam: Exam) -> list[str]:
    """Ô còn thiếu câu (theo thứ tự ô), rồi câu trả lời ngắn chưa được SymPy kiểm (BUG-003); rỗng = duyệt được."""
    problems = []
    for row in sorted(exam.matrix.cells, key=lambda c: c.sort_order):
        missing = missing_count(exam, row)
        if missing > 0:
            unit = row.content_unit or "; ".join(dict.fromkeys(u for u in row.statement_units or () if u))
            topic = f"{row.topic} – {unit}" if unit else row.topic
            part = PART_OF_TYPE[row.question_type]
            problems.append(f"Ô {row.sort_order} (Phần {part}, {topic}, {row.level.value}): thiếu {missing} câu")
    for q in sorted(exam.questions, key=lambda q: q.position):
        if not sympy_checked(q):
            problems.append(f"Câu {q.position} (Phần III): đáp án chưa được SymPy kiểm từ dữ kiện của đề")
    return problems


def sympy_checked(question: ExamQuestion) -> bool:
    """BUG-003: a generated short answer needs a SymPy expression that computes it; a teacher edit drops that result
    on purpose (edit_question), and the teacher then vouches for the answer."""
    if question.content.get("type") != "short_answer" or question.original is not None:
        return True
    check = question.content.get("check") or {}
    return check.get("verified") is True and not restates_answer(check.get("expr"))


def exam_stems(exam: Exam) -> tuple[str, ...]:
    """BUG-005: stems of the exam's questions in order; a regenerated or filled question must not repeat them."""
    return tuple(q.content.get("stem", "") for q in sorted(exam.questions, key=lambda q: q.position))


def run_for(exam: Exam, row: MatrixCell):
    [run] = [r for r in exam.cell_runs if r.matrix_cell_id == row.id]
    return run


def fill_cell_questions(exam: Exam, row: MatrixCell, rag: QuestionGenerator):
    """Bù đủ số câu thiếu: RAG trả thiếu thì hỏi tiếp (tối đa FILL_ROUNDS lượt), dừng khi lượt không thêm câu."""
    need = missing_count(exam, row)
    total = generate_cell(replace(cell_of(exam.matrix, row, need, personal=exam.is_personal), previous_stems=exam_stems(exam)), rag)
    for _ in range(FILL_ROUNDS - 1):
        left = need - len(total.questions)
        if left <= 0 or total.error or not total.questions:
            break
        stems = exam_stems(exam) + tuple(q["stem"] for q in total.questions)
        more = generate_cell(replace(cell_of(exam.matrix, row, left, personal=exam.is_personal), previous_stems=stems), rag)
        total.questions += more.questions
        total.rejected_count += more.rejected_count
        total.error = more.error
    return total


def run_regeneration(
    session_factory: sessionmaker,
    exam_id: uuid.UUID,
    matrix_cell_id: uuid.UUID,
    question_id: uuid.UUID | None,
    rag: QuestionGenerator,
) -> None:
    """Sinh lại một câu (question_id) hoặc bù các câu còn thiếu của một ô (question_id = None).

    RAG lỗi hoặc không trả câu hợp lệ thì câu cũ giữ nguyên, lỗi ghi vào ô.
    Lỗi bất ngờ cũng không làm đề kẹt `generating`: đề trở về trạng thái theo số câu hiện có.
    """
    try:
        with session_factory() as session:
            exam = session.get(Exam, exam_id)
            row = session.get(MatrixCell, matrix_cell_id)
            target = session.get(ExamQuestion, question_id) if question_id else None
            if target:
                result = generate_cell(replace(cell_of(exam.matrix, row, 1, personal=exam.is_personal), previous_stems=exam_stems(exam)), rag)
            else:
                result = fill_cell_questions(exam, row, rag)
            run = run_for(exam, row)
            run.rejected_count = result.rejected_count
            run.error_message = result.error or (None if result.questions else NO_VALID_QUESTION)
            if target and result.questions:
                target.content, target.original = result.questions[0], None
            elif not target:
                last = max((q.position for q in exam.questions), default=0)
                for offset, content in enumerate(result.questions, start=1):
                    exam.questions.append(
                        ExamQuestion(matrix_cell_id=row.id, position=last + offset, content=content)
                    )
            settle(exam)
            session.commit()
    except Exception:
        log.exception("sinh lại câu lỗi, đề %s", exam_id)
        _recover_regeneration(session_factory, exam_id, matrix_cell_id)


def _recover_regeneration(session_factory: sessionmaker, exam_id: uuid.UUID, matrix_cell_id: uuid.UUID) -> None:
    """Trả đề khỏi `generating` sau lỗi bất ngờ: giữ nguyên các câu, ghi lỗi chung vào ô."""
    try:
        with session_factory() as session:
            exam = session.get(Exam, exam_id)
            if exam is None:
                return
            for run in exam.cell_runs:
                if run.matrix_cell_id == matrix_cell_id:
                    run.error_message = GENERIC_ERROR
            settle(exam)
            session.commit()
    except Exception:
        log.exception("không ghi được trạng thái lỗi cho đề %s", exam_id)
