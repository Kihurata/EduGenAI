"""GV/admin tải đề mẫu (PDF/DOCX/JSON), duyệt bản nháp rồi xác nhận cho RAG học (T-050).
GV chỉ thấy và sửa đề mình tải (RAG cũng chỉ cho GV đó truy xuất); admin thấy mọi đề trong trường."""

import hashlib
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api.deps import DB, CurrentUser, can_manage, get_in_school, not_found, read_upload
from app.db.session import get_session_factory
from app.models import SampleExam, Subject, User
from app.models.enums import IngestStatus, UserRole
from app.services.draft_extractor import DraftExtractor, get_draft_extractor
from app.services.rag_client import get_rag_client
from app.services.rag_ingest import Ingester
from app.services.sample_exams import confirm, extract_draft, refresh_status, set_draft
from app.services.storage import LocalStorage, get_storage

router = APIRouter(prefix="/admin/sample-exams", tags=["sample-exams"])

ACCEPTED_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/json": ".json",
}

Rag = Annotated[Ingester, Depends(get_rag_client)]
Extractor = Annotated[DraftExtractor, Depends(get_draft_extractor)]


class SampleExamOut(BaseModel):
    id: uuid.UUID
    title: str
    subject: str
    grade: int
    original_filename: str
    mime_type: str
    size_bytes: int
    storage_key: str
    status: IngestStatus
    error_message: str | None
    created_at: datetime
    draft: dict[str, Any] | None
    issues: list[dict[str, Any]]

    @classmethod
    def of(cls, s: SampleExam) -> "SampleExamOut":
        return cls(
            id=s.id, title=s.title, subject=s.subject.code, grade=s.grade,
            original_filename=s.original_filename, mime_type=s.mime_type, size_bytes=s.size_bytes,
            storage_key=s.storage_key, status=s.status, error_message=s.error_message,
            created_at=s.created_at, draft=s.draft, issues=s.draft_issues or [],
        )  # fmt: skip


class DraftIn(BaseModel):
    draft: dict[str, Any]


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_sample_exam(
    file: UploadFile,
    title: Annotated[str, Form(min_length=1, max_length=255)],
    grade: Annotated[int, Form(ge=10, le=12)],
    subject: Annotated[str, Form(min_length=1, max_length=32)],
    db: DB,
    user: CurrentUser,
    background: BackgroundTasks,
    extractor: Extractor,
    factory: Annotated[sessionmaker, Depends(get_session_factory)],
    storage: Annotated[LocalStorage, Depends(get_storage)],
) -> SampleExamOut:
    ext = ACCEPTED_TYPES.get(file.content_type or "")
    if ext is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Đề mẫu chỉ nhận file PDF, DOCX hoặc JSON")
    subject_row = db.scalar(select(Subject).where(Subject.code == subject))
    if subject_row is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Môn '{subject}' chưa có trong hệ thống")
    data = await read_upload(file)
    checksum = hashlib.sha256(data).hexdigest()
    duplicate = select(SampleExam.id).where(
        SampleExam.school_id == user.school_id, SampleExam.checksum_sha256 == checksum
    )
    if db.scalar(duplicate):
        raise HTTPException(status.HTTP_409_CONFLICT, "File này đã được tải lên trước đó")
    sample_id = uuid.uuid4()
    key = f"sample_exams/{sample_id}/source{ext}"
    storage.save(key, data)
    sample = SampleExam(
        id=sample_id, school_id=user.school_id, uploaded_by=user.id, subject_id=subject_row.id,
        grade=grade, title=title, original_filename=file.filename or f"de_mau{ext}",
        mime_type=file.content_type, size_bytes=len(data), storage_key=key, checksum_sha256=checksum,
        status=IngestStatus.pending,
    )  # fmt: skip
    db.add(sample)
    db.commit()
    background.add_task(extract_draft, factory, sample_id, extractor, storage)
    return SampleExamOut.of(sample)


@router.get("")
def list_sample_exams(db: DB, user: CurrentUser, rag: Rag) -> list[SampleExamOut]:
    query = select(SampleExam).where(SampleExam.school_id == user.school_id).order_by(SampleExam.created_at.desc())
    if user.role is not UserRole.admin:
        query = query.where(SampleExam.uploaded_by == user.id)
    samples = db.scalars(query).all()
    for s in samples:
        refresh_status(s, rag)
    db.commit()
    return [SampleExamOut.of(s) for s in samples]


def _own(db: DB, sample_id: uuid.UUID, user: User) -> SampleExam:
    """Đề của GV đang đăng nhập, hoặc mọi đề trong trường với admin; đề của người khác coi như không có."""
    sample = get_in_school(db, SampleExam, sample_id, user, "đề mẫu")
    if not can_manage(user, sample.uploaded_by):
        raise not_found("đề mẫu")
    return sample


@router.get("/{sample_id}")
def read_sample_exam(sample_id: uuid.UUID, db: DB, user: CurrentUser, rag: Rag) -> SampleExamOut:
    sample = _own(db, sample_id, user)
    refresh_status(sample, rag)
    db.commit()
    return SampleExamOut.of(sample)


def _with_draft(db: DB, sample_id: uuid.UUID, user: CurrentUser) -> SampleExam:
    sample = _own(db, sample_id, user)
    if sample.draft is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Đề mẫu chưa có bản nháp để duyệt")
    return sample


@router.put("/{sample_id}/draft")
def save_draft(sample_id: uuid.UUID, body: DraftIn, db: DB, user: CurrentUser) -> SampleExamOut:
    """GV sửa đề bài, đáp án, chủ đề, mức độ, lớp, loại đề…; sửa đề đã nạp thì phải xác nhận lại."""
    sample = _with_draft(db, sample_id, user)
    set_draft(sample, body.draft)
    sample.status, sample.error_message = IngestStatus.needs_review, None
    db.commit()
    return SampleExamOut.of(sample)


@router.post("/{sample_id}/confirm")
def confirm_sample_exam(sample_id: uuid.UUID, db: DB, user: CurrentUser, rag: Rag) -> SampleExamOut:
    sample = _with_draft(db, sample_id, user)
    if sample.draft_issues:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Bản nháp còn lỗi, sửa hết rồi mới xác nhận")
    confirm(sample, rag)
    refresh_status(sample, rag)
    db.commit()
    return SampleExamOut.of(sample)
