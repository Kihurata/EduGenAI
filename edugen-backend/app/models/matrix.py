import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin
from app.models.catalog import Subject
from app.models.enums import Level, MatrixStatus, QuestionType
from app.models.types import pg_enum


class ExamMatrix(UUIDPkMixin, TimestampMixin, Base):
    """Ma trận GV tải lên dạng ảnh/PDF: file gốc → markdown (marker) → các ô.

    Môn, lớp, tên đọc từ phần đầu ma trận nên null tới khi parse xong.
    """

    __tablename__ = "exam_matrices"
    __table_args__ = (CheckConstraint("grade BETWEEN 10 AND 12", name="grade_range"),)

    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subjects.id"))
    grade: Mapped[int | None] = mapped_column(SmallInteger)
    name: Mapped[str | None] = mapped_column(String(255))

    source_filename: Mapped[str] = mapped_column(String(255))
    source_mime_type: Mapped[str] = mapped_column(String(100))
    source_storage_key: Mapped[str] = mapped_column(String(512), unique=True)

    status: Mapped[MatrixStatus] = mapped_column(
        pg_enum(MatrixStatus, "matrix_status"), default=MatrixStatus.uploaded
    )
    # Output marker, giữ lại để parse lại khi parser đổi mà không phải chạy marker.
    markdown: Mapped[str | None] = mapped_column(Text)
    parse_issues: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    subject: Mapped[Subject | None] = relationship()
    cells: Mapped[list["MatrixCell"]] = relationship(
        back_populates="matrix",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MatrixCell.sort_order",
    )


class MatrixCell(UUIDPkMixin, Base):
    """Một ô gửi RAG: chủ đề (+ đơn vị kiến thức) × dạng × mức độ → số CÂU.

    Ô gộp dọc trùm nhiều đơn vị kiến thức thì gán cho cả chủ đề (content_unit null).
    Đúng–Sai: statement_levels là mức của ý a–d, level là mức cao nhất; statement_units là đơn vị kiến
    thức của từng ý (một câu có thể rải nhiều đơn vị, khi đó content_unit null).
    """

    __tablename__ = "matrix_cells"
    __table_args__ = (CheckConstraint("question_count > 0", name="count_positive"),)

    matrix_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_matrices.id", ondelete="CASCADE"), index=True
    )
    sort_order: Mapped[int] = mapped_column(SmallInteger)
    topic: Mapped[str] = mapped_column(String(255))
    content_unit: Mapped[str | None] = mapped_column(String(255))
    question_type: Mapped[QuestionType] = mapped_column(pg_enum(QuestionType, "question_type"))
    level: Mapped[Level] = mapped_column(pg_enum(Level, "question_level"))
    statement_levels: Mapped[list[str] | None] = mapped_column(JSONB)
    statement_units: Mapped[list[str | None] | None] = mapped_column(JSONB)
    question_count: Mapped[int] = mapped_column(SmallInteger)
    competency_codes: Mapped[list[str]] = mapped_column(JSONB, default=list)

    matrix: Mapped[ExamMatrix] = relationship(back_populates="cells")
