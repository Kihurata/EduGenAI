"""Ngân hàng ĐỀ của trường: đề chính thức tổ chuyên môn đã thống nhất, lưu kèm ma trận gốc.

Chỉ admin nạp, sửa, gỡ. Đề nạp vào được gửi RAG học. GV chỉ thấy, mở, tải đề admin đã bật
cờ hiển thị; đề tạm ẩn coi như không tồn tại với GV.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import DB, Admin, CurrentUser, get_in_school, not_found
from app.api.v1.exams import ExamOut, download, download_variants
from app.api.v1.matrices import MatrixOut
from app.db.session import get_session_factory
from app.models import Exam, ExamBankEntry, ExamMatrix, User
from app.models.enums import ExamStatus, ExportVariant, IngestStatus, UserRole
from app.services.bank import refresh_status, send_exam_to_rag
from app.services.rag_client import get_rag_client
from app.services.rag_ingest import Ingester
from app.services.storage import LocalStorage, get_storage

router = APIRouter(prefix="/bank", tags=["bank"])

Rag = Annotated[Ingester, Depends(get_rag_client)]
Storage = Annotated[LocalStorage, Depends(get_storage)]


class BankIn(BaseModel):
    exam_id: uuid.UUID
    is_visible: bool = False  # mặc định tạm ẩn


class BankPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    duration_minutes: int | None = Field(None, gt=0, le=300)
    is_visible: bool | None = None


class SavedBy(BaseModel):
    id: uuid.UUID
    full_name: str


class BankEntryOut(BaseModel):
    id: uuid.UUID
    exam_id: uuid.UUID
    title: str
    duration_minutes: int
    subject: str
    grade: int
    matrix_name: str | None
    is_visible: bool
    rag_status: IngestStatus
    error_message: str | None
    saved_by: SavedBy
    saved_at: datetime

    @classmethod
    def of(cls, entry: ExamBankEntry, saver: User) -> "BankEntryOut":
        exam = entry.exam
        return cls(
            id=entry.id, exam_id=exam.id, title=exam.title, duration_minutes=exam.duration_minutes,
            subject=exam.matrix.subject.name, grade=exam.matrix.grade, matrix_name=exam.matrix.name,
            is_visible=entry.is_visible, rag_status=entry.rag_status, error_message=entry.error_message,
            saved_by=SavedBy(id=saver.id, full_name=saver.full_name), saved_at=entry.saved_at,
        )  # fmt: skip


class BankDetailOut(BankEntryOut):
    exam: ExamOut
    matrix: MatrixOut


def _out(db: Session, entry: ExamBankEntry) -> BankEntryOut:
    return BankEntryOut.of(entry, db.get(User, entry.saved_by))


def get_entry(db: Session, entry_id: uuid.UUID, user: User) -> ExamBankEntry:
    """Đề trong ngân hàng của trường; GV không thấy đề đang tạm ẩn."""
    entry = get_in_school(db, ExamBankEntry, entry_id, user, "đề trong ngân hàng")
    if not entry.is_visible and user.role is not UserRole.admin:
        raise not_found("đề trong ngân hàng")
    return entry


@router.post("", status_code=status.HTTP_201_CREATED)
def add_to_bank(
    body: BankIn,
    db: DB,
    admin: Admin,
    background: BackgroundTasks,
    factory: Annotated[sessionmaker, Depends(get_session_factory)],
    rag: Rag,
    storage: Storage,
) -> BankEntryOut:
    exam = get_in_school(db, Exam, body.exam_id, admin, "đề")
    if exam.status is not ExamStatus.approved:
        raise HTTPException(status.HTTP_409_CONFLICT, "Chỉ nạp được đề đã duyệt")
    if db.scalar(select(ExamBankEntry.id).where(ExamBankEntry.exam_id == exam.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Đề đã có trong ngân hàng")
    entry = ExamBankEntry(
        school_id=admin.school_id, exam_id=exam.id, saved_by=admin.id, is_visible=body.is_visible,
        rag_status=IngestStatus.pending,
    )  # fmt: skip
    db.add(entry)
    db.commit()
    db.refresh(entry)
    background.add_task(send_exam_to_rag, factory, entry.id, rag, storage)
    return _out(db, entry)


@router.get("")
def list_bank(db: DB, user: CurrentUser, rag: Rag, grade: int | None = None) -> list[BankEntryOut]:
    query = (
        select(ExamBankEntry)
        .join(Exam, ExamBankEntry.exam_id == Exam.id)
        .join(ExamMatrix, Exam.matrix_id == ExamMatrix.id)
        .where(ExamBankEntry.school_id == user.school_id)
        .order_by(ExamBankEntry.saved_at.desc())
    )
    if user.role is not UserRole.admin:
        query = query.where(ExamBankEntry.is_visible.is_(True))
    if grade is not None:
        query = query.where(ExamMatrix.grade == grade)
    entries = list(db.scalars(query))
    if user.role is UserRole.admin:
        for entry in entries:
            refresh_status(entry, rag)
        db.commit()
    return [_out(db, e) for e in entries]


@router.get("/{entry_id}")
def read_entry(entry_id: uuid.UUID, db: DB, user: CurrentUser, rag: Rag) -> BankDetailOut:
    entry = get_entry(db, entry_id, user)
    if user.role is UserRole.admin:
        refresh_status(entry, rag)
        db.commit()
    return BankDetailOut(
        **_out(db, entry).model_dump(), exam=ExamOut.of(entry.exam), matrix=MatrixOut.of(entry.exam.matrix)
    )


@router.get("/{entry_id}/export")
def export_entry(
    entry_id: uuid.UUID,
    variant: ExportVariant,
    db: DB,
    user: CurrentUser,
    storage: Storage,
    code: str | None = None,
) -> Response:
    return download(db, storage, get_entry(db, entry_id, user).exam, variant, code)


@router.get("/{entry_id}/export-variants")
def export_entry_variants(
    entry_id: uuid.UUID, variant: ExportVariant, codes: str, db: DB, user: CurrentUser, storage: Storage
) -> Response:
    return download_variants(db, storage, get_entry(db, entry_id, user).exam, variant, codes)


@router.patch("/{entry_id}")
def update_entry(entry_id: uuid.UUID, body: BankPatch, db: DB, admin: Admin) -> BankEntryOut:
    entry = get_entry(db, entry_id, admin)
    if body.title is not None:
        entry.exam.title = body.title
    if body.duration_minutes is not None:
        entry.exam.duration_minutes = body.duration_minutes
    if body.is_visible is not None:
        entry.is_visible = body.is_visible
    db.commit()
    return _out(db, entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: uuid.UUID, db: DB, admin: Admin) -> Response:
    """Gỡ đề khỏi ngân hàng; đề vẫn còn trong danh sách đề của người tạo."""
    db.delete(get_entry(db, entry_id, admin))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

