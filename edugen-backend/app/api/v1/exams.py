"""Sinh đề từ ma trận đã xác nhận (job nền), GV duyệt đề (F-05) và xuất DOCX đề đã duyệt."""

import io
import uuid
import zipfile
from datetime import datetime
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import DB, CurrentUser, can_manage, get_in_school, not_found
from app.api.v1.matrices import get_matrix
from app.api.v1.schemas import Accepted
from app.core.errors import LLMError
from app.db.session import get_session_factory
from app.domain.exam_document import VARIANT_LABELS
from app.domain.exam_structure import PART_OF_TYPE
from app.domain.exam_variant import is_valid_code
from app.domain.generation import QuestionGenerator
from app.models import Exam, ExamBankEntry, ExamQuestion, User
from app.models.enums import (
    CellRunStatus,
    ExamStatus,
    ExportVariant,
    MatrixStatus,
    QuestionType,
    UserRole,
)
from app.services.exam_jobs import DOCX_MIME, export_exam, run_exam_generation, settle, variant_questions
from app.services.exam_review import (
    approval_problems,
    edit_question,
    missing_count,
    run_regeneration,
)
from app.services.rag_client import get_rag_client
from app.services.storage import LocalStorage, get_storage

router = APIRouter(prefix="/exams", tags=["exams"])


class ExamIn(BaseModel):
    matrix_id: uuid.UUID
    duration_minutes: int = Field(gt=0, le=300)  # GV nhập
    title: str | None = Field(None, min_length=1, max_length=255)  # mặc định = tên ma trận


class CellRunOut(BaseModel):
    matrix_cell_id: uuid.UUID
    sort_order: int
    status: CellRunStatus
    question_count: int  # số câu ô cần; thiếu = question_count - valid_count
    valid_count: int
    rejected_count: int
    error_message: str | None


class QuestionOut(BaseModel):
    id: uuid.UUID
    position: int
    part: str
    matrix_cell_id: uuid.UUID
    content: dict[str, Any]
    edited: bool  # GV đã sửa tay

    @classmethod
    def of(cls, q: ExamQuestion) -> "QuestionOut":
        return cls(
            id=q.id, position=q.position, matrix_cell_id=q.matrix_cell_id, content=q.content,
            part=PART_OF_TYPE[QuestionType(q.content["type"])], edited=q.original is not None,
        )  # fmt: skip


class ExamOut(BaseModel):
    id: uuid.UUID
    matrix_id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    duration_minutes: int
    subject: str | None  # mã môn của ma trận (T-064), để bản xem trước ghi đúng môn
    grade: int | None
    status: ExamStatus
    cells_done: int
    cells_total: int
    created_at: datetime
    cell_runs: list[CellRunOut]
    questions: list[QuestionOut]

    @classmethod
    def of(cls, e: Exam) -> "ExamOut":
        runs = sorted(e.cell_runs, key=lambda r: r.matrix_cell.sort_order)
        return cls(
            id=e.id, matrix_id=e.matrix_id, owner_id=e.owner_id, title=e.title,
            duration_minutes=e.duration_minutes, subject=e.matrix.subject.code if e.matrix.subject else None,
            grade=e.matrix.grade, status=e.status, cells_done=e.cells_done,
            cells_total=e.cells_total, created_at=e.created_at,
            cell_runs=[
                CellRunOut(
                    matrix_cell_id=r.matrix_cell_id, sort_order=r.matrix_cell.sort_order,
                    status=r.status, question_count=r.matrix_cell.question_count,
                    valid_count=r.valid_count, rejected_count=r.rejected_count,
                    error_message=r.error_message,
                )
                for r in runs
            ],
            questions=[QuestionOut.of(q) for q in e.questions],
        )  # fmt: skip


def get_exam(db: Session, exam_id: uuid.UUID, user: User) -> Exam:
    """Người tạo/admin cùng trường; GV khác xem được khi đề đã vào ngân hàng và đang hiển thị."""
    exam = get_in_school(db, Exam, exam_id, user, "đề")
    if can_manage(user, exam.owner_id):
        return exam
    shown = select(ExamBankEntry.id).where(
        ExamBankEntry.exam_id == exam.id, ExamBankEntry.is_visible.is_(True)
    )
    if db.scalar(shown) is None:
        raise not_found("đề")
    return exam


MAX_VARIANT_CODES = 4  # khớp MAX_EXAM_CODES của frontend
ZIP_MIME = "application/zip"


def attachment(data: bytes, filename: str, media_type: str) -> Response:
    return Response(
        data, media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )  # fmt: skip


def check_codes(codes: list[str]) -> list[str]:
    """Mã đề hợp lệ (1–8 chữ/số), bỏ trùng giữ thứ tự; sai → 422."""
    bad = [c for c in codes if not is_valid_code(c)]
    if bad or not codes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Mã đề gồm 1–8 chữ hoặc số, không hợp lệ: {bad or codes}"
        )
    return list(dict.fromkeys(codes))


def download(
    db: Session, storage: LocalStorage, exam: Exam, variant: ExportVariant, code: str | None = None
) -> Response:
    if exam.status is not ExamStatus.approved:
        raise HTTPException(status.HTTP_409_CONFLICT, "Đề chưa được duyệt, chưa xuất được")
    if code is not None:
        check_codes([code])
    data, filename = export_exam(db, storage, exam, variant, code)
    return attachment(data, filename, DOCX_MIME)


def download_variants(
    db: Session, storage: LocalStorage, exam: Exam, variant: ExportVariant, codes: str
) -> Response:
    """Nhiều mã đề trong một file zip (mỗi mã một DOCX)."""
    if exam.status is not ExamStatus.approved:
        raise HTTPException(status.HTTP_409_CONFLICT, "Đề chưa được duyệt, chưa xuất được")
    wanted = check_codes([c.strip() for c in codes.split(",") if c.strip()])
    if len(wanted) > MAX_VARIANT_CODES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Tối đa {MAX_VARIANT_CODES} mã đề mỗi lần xuất"
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for code in wanted:
            data, filename = export_exam(db, storage, exam, variant, code)
            archive.writestr(filename, data)
    name = f"{exam.title} - {len(wanted)} mã đề - {VARIANT_LABELS[variant]}.zip"  # bản HS/GV ghi rõ ở cuối tên
    return attachment(buffer.getvalue(), name, ZIP_MIME)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_exam(
    body: ExamIn,
    db: DB,
    user: CurrentUser,
    background: BackgroundTasks,
    factory: Annotated[sessionmaker, Depends(get_session_factory)],
    rag: Annotated[QuestionGenerator, Depends(get_rag_client)],
) -> Accepted:
    matrix = get_matrix(db, body.matrix_id, user)
    if matrix.status is not MatrixStatus.confirmed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ma trận chưa được xác nhận")
    exam = Exam(
        school_id=user.school_id, matrix_id=matrix.id, owner_id=user.id,
        title=body.title or matrix.name or "Đề kiểm tra", duration_minutes=body.duration_minutes,
        status=ExamStatus.generating, cells_done=0, cells_total=len(matrix.cells),
    )  # fmt: skip
    db.add(exam)
    db.commit()
    background.add_task(run_exam_generation, factory, exam.id, rag)
    return Accepted(id=exam.id, status=exam.status.value)


@router.get("")
def list_exams(db: DB, user: CurrentUser) -> list[ExamOut]:
    """GV: đề của mình. Admin: mọi đề trong trường, để chọn đề nạp vào ngân hàng."""
    query = select(Exam).where(Exam.school_id == user.school_id).order_by(Exam.created_at.desc())
    if user.role is not UserRole.admin:
        query = query.where(Exam.owner_id == user.id)
    return [ExamOut.of(e) for e in db.scalars(query)]


@router.get("/{exam_id}")
def read_exam(exam_id: uuid.UUID, db: DB, user: CurrentUser) -> ExamOut:
    return ExamOut.of(get_exam(db, exam_id, user))


class VariantQuestionOut(BaseModel):
    position: int  # thứ tự trong cả đề theo mã đề; "Câu n" vẫn tính lại theo phần
    part: str
    content: dict[str, Any]


class VariantOut(BaseModel):
    code: str
    questions: list[VariantQuestionOut]


@router.get("/{exam_id}/variant")
def read_variant(exam_id: uuid.UUID, code: str, db: DB, user: CurrentUser) -> VariantOut:
    """Các câu của đề theo mã đề, đúng thứ tự file xuất ra, để xem trước. Không đổi dữ liệu."""
    [code] = check_codes([code])
    contents = variant_questions(get_exam(db, exam_id, user), code)
    return VariantOut(
        code=code,
        questions=[
            VariantQuestionOut(position=i, part=PART_OF_TYPE[QuestionType(c["type"])], content=c)
            for i, c in enumerate(contents, start=1)
        ],
    )


@router.get("/{exam_id}/export")
def export(
    exam_id: uuid.UUID,
    variant: ExportVariant,
    db: DB,
    user: CurrentUser,
    storage: Annotated[LocalStorage, Depends(get_storage)],
    code: str | None = None,
) -> Response:
    """Không có `code`: bản gốc. Có `code` (mã đề): câu và phương án xáo theo mã, mã in trên đề."""
    return download(db, storage, get_exam(db, exam_id, user), variant, code)


@router.get("/{exam_id}/export-variants")
def export_variants(
    exam_id: uuid.UUID,
    variant: ExportVariant,
    codes: str,
    db: DB,
    user: CurrentUser,
    storage: Annotated[LocalStorage, Depends(get_storage)],
) -> Response:
    """`codes`: các mã đề cách nhau bằng dấu phẩy, ví dụ 101,102,103; trả zip mỗi mã một DOCX."""
    return download_variants(db, storage, get_exam(db, exam_id, user), variant, codes)


# --- GV duyệt đề (F-05) ---

Rag = Annotated[QuestionGenerator, Depends(get_rag_client)]
Factory = Annotated[sessionmaker, Depends(get_session_factory)]


def get_reviewable(db: Session, exam_id: uuid.UUID, user: User) -> Exam:
    """Đề người tạo/admin được sửa: không đang sinh, chưa duyệt."""
    exam = get_exam(db, exam_id, user)
    if not can_manage(user, exam.owner_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ người tạo đề hoặc admin được duyệt đề")
    if exam.status is ExamStatus.generating:
        raise HTTPException(status.HTTP_409_CONFLICT, "Đề đang sinh, chờ xong rồi thao tác")
    if exam.status is ExamStatus.approved:
        raise HTTPException(status.HTTP_409_CONFLICT, "Đề đã duyệt, không sửa được")
    return exam


def get_question(exam: Exam, question_id: uuid.UUID) -> ExamQuestion:
    for question in exam.questions:
        if question.id == question_id:
            return question
    raise not_found("câu hỏi")


@router.put("/{exam_id}/questions/{question_id}")
def update_question(
    exam_id: uuid.UUID, question_id: uuid.UUID, body: dict[str, Any], db: DB, user: CurrentUser, rag: Rag
) -> QuestionOut:
    """Body: cả câu theo format của BE (domain/question.py). Sai → 422, detail = danh sách lỗi."""
    question = get_question(get_reviewable(db, exam_id, user), question_id)
    try:
        errors = edit_question(question, body, rag)
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Chưa kiểm được câu sửa: {exc}") from exc
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, errors)
    db.commit()
    return QuestionOut.of(question)


@router.delete("/{exam_id}/questions/{question_id}")
def delete_question(exam_id: uuid.UUID, question_id: uuid.UUID, db: DB, user: CurrentUser) -> ExamOut:
    """Xoá câu: ô thành thiếu, không tự bù (GV bấm sinh lại/bù ô nếu muốn)."""
    exam = get_reviewable(db, exam_id, user)
    exam.questions.remove(get_question(exam, question_id))
    settle(exam)
    db.commit()
    return ExamOut.of(exam)


def start_regeneration(
    db: Session, background: BackgroundTasks, factory: sessionmaker, rag: QuestionGenerator,
    exam: Exam, matrix_cell_id: uuid.UUID, question_id: uuid.UUID | None,
) -> Accepted:  # fmt: skip
    # Chuyển trạng thái bằng một UPDATE có điều kiện để bấm đúp không khởi động hai job.
    claimed = db.execute(
        update(Exam).where(Exam.id == exam.id, Exam.status.not_in((ExamStatus.generating, ExamStatus.approved)))
        .values(status=ExamStatus.generating)
    )  # fmt: skip
    db.commit()
    if claimed.rowcount == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Đề đang sinh, chờ xong rồi thao tác")
    db.refresh(exam)
    background.add_task(run_regeneration, factory, exam.id, matrix_cell_id, question_id, rag)
    return Accepted(id=exam.id, status=exam.status.value)


@router.post("/{exam_id}/questions/{question_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
def regenerate_question(
    exam_id: uuid.UUID, question_id: uuid.UUID, db: DB, user: CurrentUser,
    background: BackgroundTasks, factory: Factory, rag: Rag,
) -> Accepted:  # fmt: skip
    """Sinh lại một câu cùng ô; câu mới thay đúng vị trí. Hỏi lại GET đề đến khi hết `generating`."""
    exam = get_reviewable(db, exam_id, user)
    question = get_question(exam, question_id)
    return start_regeneration(db, background, factory, rag, exam, question.matrix_cell_id, question.id)


@router.post("/{exam_id}/cells/{matrix_cell_id}/fill", status_code=status.HTTP_202_ACCEPTED)
def fill_cell(
    exam_id: uuid.UUID, matrix_cell_id: uuid.UUID, db: DB, user: CurrentUser,
    background: BackgroundTasks, factory: Factory, rag: Rag,
) -> Accepted:  # fmt: skip
    """Sinh đúng số câu còn thiếu của một ô (ô bị xoá câu, ô RAG trả thiếu hoặc lỗi)."""
    exam = get_reviewable(db, exam_id, user)
    row = next((c for c in exam.matrix.cells if c.id == matrix_cell_id), None)
    if row is None:
        raise not_found("ô ma trận")
    if missing_count(exam, row) <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ô này đã đủ câu")
    return start_regeneration(db, background, factory, rag, exam, row.id, None)


@router.post("/{exam_id}/approve")
def approve(exam_id: uuid.UUID, db: DB, user: CurrentUser) -> ExamOut:
    """Duyệt khi mọi ô đủ câu; không thì 409, detail = danh sách ô thiếu. Duyệt xong khoá sửa."""
    exam = get_reviewable(db, exam_id, user)
    problems = approval_problems(exam)
    if problems:
        raise HTTPException(status.HTTP_409_CONFLICT, problems)
    exam.status = ExamStatus.approved
    db.commit()
    return ExamOut.of(exam)
