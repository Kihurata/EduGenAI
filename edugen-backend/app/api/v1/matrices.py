"""Ma trận của GV: tải lên (job marker nền) → xem/sửa ô → xác nhận."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import (
    DB,
    CurrentUser,
    can_manage,
    get_in_school,
    not_found,
    read_upload,
)
from app.api.v1.schemas import Accepted, IssueOut
from app.db.session import get_session_factory
from app.domain.exam_structure import STATEMENTS_PER_TRUE_FALSE
from app.domain.matrix_reader import ParsedCell
from app.models import ExamMatrix, MatrixCell, User
from app.models.enums import LEVEL_ORDER, Level, MatrixStatus, QuestionType
from app.services.matrix_converter import MatrixConverter, get_matrix_converter
from app.services.matrix_jobs import process_matrix, update_cells
from app.services.storage import LocalStorage, get_storage

DEMO_GRADE = 12  # bản demo chỉ sinh đề Toán lớp 12; không tự đổi lớp của ma trận

router = APIRouter(prefix="/matrices", tags=["matrices"])

ACCEPTED_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "application/pdf": ".pdf"}


class CellIn(BaseModel):
    topic: str = Field(min_length=1, max_length=255)
    content_unit: str | None = Field(None, max_length=255)  # None = cả chủ đề
    type: QuestionType
    level: Level  # Đúng–Sai: BE tự lấy mức cao nhất của 4 ý
    count: int = Field(gt=0, le=50)
    statement_levels: list[Level] | None = None
    # Đúng–Sai: đơn vị kiến thức của ý a–d; null (cả danh sách hoặc một ý) = theo content_unit / cả chủ đề
    statement_units: list[Annotated[str, Field(max_length=255)] | None] | None = None
    competency_codes: list[str] = []

    @model_validator(mode="after")
    def _statements(self) -> "CellIn":
        if self.type is QuestionType.true_false:
            if not self.statement_levels or len(self.statement_levels) != STATEMENTS_PER_TRUE_FALSE:
                raise ValueError("Câu Đúng – Sai cần mức độ cho đủ 4 ý a–d")
            if self.statement_units is not None and len(self.statement_units) != STATEMENTS_PER_TRUE_FALSE:
                raise ValueError("Câu Đúng – Sai cần nội dung cho đủ 4 ý a–d")
            self.level = max(self.statement_levels, key=LEVEL_ORDER.index)
        elif self.statement_levels is not None or self.statement_units is not None:
            raise ValueError("Chỉ câu Đúng – Sai mới có mức độ và nội dung từng ý")
        return self

    def to_parsed(self) -> ParsedCell:
        return ParsedCell(
            self.type, self.topic, self.content_unit or None, self.level, self.count,
            tuple(self.statement_levels) if self.statement_levels else None,
            tuple(self.competency_codes),
            statement_units=tuple(u.strip() or None if u else None for u in self.statement_units)
            if self.statement_units else None,
        )  # fmt: skip


class CellsIn(BaseModel):
    cells: list[CellIn] = Field(min_length=1)
    name: str | None = Field(None, min_length=1, max_length=255)
    grade: int | None = Field(None, ge=10, le=12)


class CellOut(BaseModel):
    id: uuid.UUID
    sort_order: int
    topic: str
    content_unit: str | None
    type: QuestionType
    level: Level
    count: int
    statement_levels: list[Level] | None
    statement_units: list[str | None] | None
    competency_codes: list[str]

    @classmethod
    def of(cls, c: MatrixCell) -> "CellOut":
        return cls(
            id=c.id, sort_order=c.sort_order, topic=c.topic, content_unit=c.content_unit,
            type=c.question_type, level=c.level, count=c.question_count,
            statement_levels=c.statement_levels, statement_units=c.statement_units,
            competency_codes=c.competency_codes or [],
        )  # fmt: skip


class MatrixSummary(BaseModel):
    id: uuid.UUID
    status: MatrixStatus
    subject: str | None
    grade: int | None
    name: str | None
    source_filename: str
    created_at: datetime

    @classmethod
    def of(cls, m: ExamMatrix) -> "MatrixSummary":
        return cls(
            id=m.id, status=m.status, subject=m.subject.code if m.subject else None,
            grade=m.grade, name=m.name, source_filename=m.source_filename, created_at=m.created_at,
        )  # fmt: skip


class MatrixOut(MatrixSummary):
    issues: list[IssueOut]
    error_message: str | None
    confirmed_at: datetime | None
    cells: list[CellOut]

    @classmethod
    def of(cls, m: ExamMatrix) -> "MatrixOut":
        return cls(
            **MatrixSummary.of(m).model_dump(),
            issues=[IssueOut(**i) for i in m.parse_issues or []],
            error_message=m.error_message, confirmed_at=m.confirmed_at,
            cells=[CellOut.of(c) for c in m.cells],
        )  # fmt: skip


def get_matrix(db: Session, matrix_id: uuid.UUID, user: User) -> ExamMatrix:
    """Ma trận của người tạo, hoặc admin cùng trường."""
    matrix = get_in_school(db, ExamMatrix, matrix_id, user, "ma trận")
    if not can_manage(user, matrix.owner_id):
        raise not_found("ma trận")
    return matrix


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_matrix(
    file: UploadFile,
    db: DB,
    user: CurrentUser,
    background: BackgroundTasks,
    factory: Annotated[sessionmaker, Depends(get_session_factory)],
    storage: Annotated[LocalStorage, Depends(get_storage)],
    converter: Annotated[MatrixConverter, Depends(get_matrix_converter)],
) -> Accepted:
    ext = ACCEPTED_TYPES.get(file.content_type or "")
    if ext is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Chỉ nhận ảnh PNG/JPG hoặc file PDF")
    data = await read_upload(file)
    matrix_id = uuid.uuid4()
    key = f"matrices/{matrix_id}/source{ext}"
    storage.save(key, data)
    matrix = ExamMatrix(
        id=matrix_id, school_id=user.school_id, owner_id=user.id,
        source_filename=file.filename or f"ma_tran{ext}", source_mime_type=file.content_type,
        source_storage_key=key,
    )  # fmt: skip
    db.add(matrix)
    db.commit()
    background.add_task(process_matrix, factory, matrix_id, converter, storage)
    return Accepted(id=matrix_id, status=MatrixStatus.uploaded.value)


@router.get("")
def list_matrices(db: DB, user: CurrentUser) -> list[MatrixSummary]:
    matrices = db.scalars(
        select(ExamMatrix).where(ExamMatrix.owner_id == user.id).order_by(ExamMatrix.created_at.desc())
    )
    return [MatrixSummary.of(m) for m in matrices]


@router.get("/{matrix_id}")
def read_matrix_detail(matrix_id: uuid.UUID, db: DB, user: CurrentUser) -> MatrixOut:
    return MatrixOut.of(get_matrix(db, matrix_id, user))


@router.put("/{matrix_id}/cells")
def edit_cells(matrix_id: uuid.UUID, body: CellsIn, db: DB, user: CurrentUser) -> MatrixOut:
    matrix = get_matrix(db, matrix_id, user)
    if matrix.status not in (MatrixStatus.parsed, MatrixStatus.invalid):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ma trận đã xác nhận hoặc chưa đọc xong, không sửa được")
    update_cells(db, matrix, [c.to_parsed() for c in body.cells], body.name, body.grade)
    db.commit()
    db.refresh(matrix)
    return MatrixOut.of(matrix)


@router.post("/{matrix_id}/confirm")
def confirm_matrix(matrix_id: uuid.UUID, db: DB, user: CurrentUser) -> MatrixOut:
    matrix = get_matrix(db, matrix_id, user)
    if matrix.status is not MatrixStatus.parsed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ma trận còn lỗi hoặc chưa đọc xong, chưa xác nhận được")
    if matrix.grade != DEMO_GRADE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Bản demo hiện chỉ hỗ trợ Toán lớp {DEMO_GRADE}. Ma trận này là lớp {matrix.grade} nên chưa xác nhận được.",
        )
    matrix.status = MatrixStatus.confirmed
    matrix.confirmed_at = datetime.now(UTC)
    db.commit()
    return MatrixOut.of(matrix)
