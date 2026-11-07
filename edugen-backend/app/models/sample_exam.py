"""Đề mẫu GV/admin tải lên để RAG học form và cách sinh đề; GV duyệt bản nháp trước khi nạp (T-050)."""

import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin
from app.models.catalog import Subject
from app.models.enums import IngestStatus
from app.models.types import pg_enum
from app.models.user import User


class SampleExam(UUIDPkMixin, TimestampMixin, Base):
    """File gốc (PDF/DOCX) nằm ở storage; BE chỉ gửi RAG và theo dõi trạng thái ingest."""

    __tablename__ = "sample_exams"
    __table_args__ = (
        # Cùng một trường không tải trùng một file hai lần.
        UniqueConstraint("school_id", "checksum_sha256"),
        CheckConstraint("grade BETWEEN 10 AND 12", name="grade_range"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
    )

    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    subject_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subjects.id"))
    grade: Mapped[int] = mapped_column(SmallInteger)
    title: Mapped[str] = mapped_column(String(255))

    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64))

    status: Mapped[IngestStatus] = mapped_column(
        pg_enum(IngestStatus, "sample_exam_status"),
        default=IngestStatus.pending,
    )
    rag_job_id: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    # Bản nháp JSON (schema app.rag.chunking.exam) và lỗi kiểm tra của nó [{"message", "question"}].
    draft: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    draft_issues: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)

    subject: Mapped[Subject] = relationship()
    uploader: Mapped[User] = relationship()
