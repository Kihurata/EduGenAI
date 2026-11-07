"""Đề sinh từ ma trận đã xác nhận, file xuất và ngân hàng đề của trường."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPkMixin
from app.models.enums import (
    CellRunStatus,
    ExamStatus,
    ExportFormat,
    ExportVariant,
    IngestStatus,
)
from app.models.matrix import ExamMatrix, MatrixCell
from app.models.types import pg_enum


class Exam(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "exams"

    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    matrix_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exam_matrices.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))  # mặc định = tên ma trận
    duration_minutes: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[ExamStatus] = mapped_column(
        pg_enum(ExamStatus, "exam_status"), default=ExamStatus.generating
    )
    # Tiến độ job sinh nền: số ô đã gọi RAG / tổng số ô.
    cells_done: Mapped[int] = mapped_column(SmallInteger, default=0)
    cells_total: Mapped[int] = mapped_column(SmallInteger)

    matrix: Mapped[ExamMatrix] = relationship()
    cell_runs: Mapped[list["ExamCellRun"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    questions: Mapped[list["ExamQuestion"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="ExamQuestion.position"
    )


class ExamCellRun(UUIDPkMixin, Base):
    """Kết quả gọi RAG của một ô trong một đề (để biết ô thiếu/lỗi)."""

    __tablename__ = "exam_cell_runs"

    exam_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), index=True
    )
    matrix_cell_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matrix_cells.id"))
    status: Mapped[CellRunStatus] = mapped_column(pg_enum(CellRunStatus, "cell_run_status"))
    valid_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    rejected_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    matrix_cell: Mapped[MatrixCell] = relationship()


class ExamQuestion(UUIDPkMixin, Base):
    """Câu trong đề: JSON RAG trả về (đã chuẩn hóa). Số "Câu n" tính lại theo phần khi xuất.

    GV sửa thì `content` là bản đã sửa, `original` giữ bản RAG trước lần sửa đầu (null = chưa sửa).
    """

    __tablename__ = "exam_questions"

    exam_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), index=True
    )
    matrix_cell_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matrix_cells.id"))
    position: Mapped[int] = mapped_column(SmallInteger)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    original: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    matrix_cell: Mapped[MatrixCell] = relationship()


class ExamExport(UUIDPkMixin, CreatedAtMixin, Base):
    """File DOCX đã xuất: bản học sinh (chỉ đề) hoặc bản giáo viên (kèm đáp án, lời giải)."""

    __tablename__ = "exam_exports"

    exam_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), index=True
    )
    variant: Mapped[ExportVariant] = mapped_column(pg_enum(ExportVariant, "export_variant"))
    format: Mapped[ExportFormat] = mapped_column(
        pg_enum(ExportFormat, "export_format"), default=ExportFormat.docx
    )
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)


class ExamBankEntry(UUIDPkMixin, Base):
    """Đề chính thức của trường (tổ chuyên môn đã thống nhất). Chỉ admin nạp, sửa, gỡ.

    Nạp vào thì gửi RAG học như đề mẫu. GV chỉ thấy đề admin đã bật cờ hiển thị.
    """

    __tablename__ = "exam_bank_entries"

    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"), index=True
    )
    exam_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), unique=True
    )
    saved_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))  # admin nạp đề
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_visible: Mapped[bool] = mapped_column(default=False)  # false = tạm ẩn với GV

    rag_status: Mapped[IngestStatus] = mapped_column(
        pg_enum(IngestStatus, "bank_ingest_status"), default=IngestStatus.pending
    )
    rag_job_id: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)

    exam: Mapped[Exam] = relationship()
