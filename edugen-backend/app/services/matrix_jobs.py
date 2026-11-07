"""Job nền xử lý ma trận: uploaded → converting → parsed | invalid | failed.

API trả matrix_id ngay sau khi lưu file; job này chạy marker, đọc ma trận và lưu các ô để
GV xem lại. Lỗi parse/lệch tổng không chặn job mà thành parse_issues (trạng thái invalid).
"""

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.matrix_reader import (
    MatrixIssue,
    ParsedCell,
    ParsedMatrix,
    check_totals,
    group_issues,
    parse_matrix_markdown,
    read_matrix,
)
from app.models import ExamMatrix, MatrixCell, Subject
from app.models.enums import MatrixStatus
from app.services.matrix_converter import ConversionError, MatrixConverter
from app.services.storage import LocalStorage

log = logging.getLogger("edugen.matrix_jobs")


def issue_dicts(issues: list[MatrixIssue]) -> list[dict[str, Any]]:
    return [{"message": i.message, "location": i.location} for i in issues]


def cell_rows(cells: list[ParsedCell]) -> list[MatrixCell]:
    return [
        MatrixCell(
            sort_order=n,
            topic=c.topic,
            content_unit=c.content_unit,
            question_type=c.type,
            level=c.level,
            statement_levels=[lv.value for lv in c.statement_levels] if c.statement_levels else None,
            statement_units=list(c.statement_units) if c.statement_units else None,
            question_count=c.count,
            competency_codes=list(c.competency_codes),
        )
        for n, c in enumerate(cells, start=1)
    ]


def apply_parsed(session: Session, matrix: ExamMatrix, parsed: ParsedMatrix) -> None:
    """Ghi môn/lớp/tên, các ô và lỗi vào ma trận; không lỗi → parsed, có lỗi → invalid."""
    issues = list(parsed.issues)
    subject = None
    if parsed.subject is not None:
        subject = session.scalar(select(Subject).where(Subject.code == parsed.subject))
        if subject is None:
            issues.append(MatrixIssue(f"Môn {parsed.subject} chưa có trong hệ thống"))
    matrix.subject_id = subject.id if subject else None
    matrix.grade = parsed.grade
    matrix.name = parsed.name
    matrix.cells = cell_rows(parsed.cells)
    matrix.parse_issues = issue_dicts(group_issues(issues))
    matrix.error_message = None
    matrix.status = MatrixStatus.invalid if issues else MatrixStatus.parsed


def update_cells(
    session: Session,
    matrix: ExamMatrix,
    cells: list[ParsedCell],
    name: str | None = None,
    grade: int | None = None,
) -> None:
    """GV sửa ô: đối chiếu lại với hàng tổng trên ma trận gốc (đọc lại từ markdown đã lưu)."""
    original = parse_matrix_markdown(matrix.markdown) if matrix.markdown else ParsedMatrix()
    edited = ParsedMatrix(
        subject=matrix.subject.code if matrix.subject else None,
        grade=grade if grade is not None else matrix.grade,
        name=name if name is not None else matrix.name,
        cells=cells,
        declared_counts=original.declared_counts,
        declared_points=original.declared_points,
        declared_required="<table" in (matrix.markdown or ""),  # JSON Gemini không có hàng tổng dạng bảng
    )
    if edited.subject is None:
        edited.issues.append(MatrixIssue("Chưa có môn của ma trận"))
    if edited.grade is None:
        edited.issues.append(MatrixIssue("Chưa có lớp của ma trận"))
    edited.issues += check_totals(edited)
    apply_parsed(session, matrix, edited)


def process_matrix(
    session_factory: sessionmaker,
    matrix_id: uuid.UUID,
    converter: MatrixConverter,
    storage: LocalStorage,
) -> None:
    with session_factory() as session:
        try:
            matrix = session.get(ExamMatrix, matrix_id)
            if matrix is None:
                return
            matrix.status = MatrixStatus.converting
            session.commit()
            markdown = converter.convert(storage.path(matrix.source_storage_key))
            matrix.markdown = markdown
            apply_parsed(session, matrix, read_matrix(markdown))
            session.commit()
        except Exception as exc:
            session.rollback()
            log.exception("xử lý ma trận lỗi")
            message = (
                f"Không đọc được file ma trận: {exc}"
                if isinstance(exc, ConversionError)
                else "Lỗi hệ thống khi xử lý ma trận, vui lòng thử lại hoặc báo quản trị viên."
            )
            _mark_failed(session_factory, matrix_id, message)


def _mark_failed(session_factory: sessionmaker, matrix_id: uuid.UUID, message: str) -> None:
    try:
        with session_factory() as session:
            matrix = session.get(ExamMatrix, matrix_id)
            if matrix is not None:
                matrix.status, matrix.error_message = MatrixStatus.failed, message
                session.commit()
    except Exception:
        log.exception("không ghi được trạng thái failed cho ma trận %s", matrix_id)
