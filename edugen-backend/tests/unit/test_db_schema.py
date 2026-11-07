"""Hợp đồng schema DB với ERD (docs/erd.mmd).

Không cần Postgres: kiểm metadata SQLAlchemy và compile DDL theo dialect PostgreSQL.
"""

import pytest
from sqlalchemy import CheckConstraint, Enum, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

import app.models  # noqa: F401 – đăng ký mọi bảng
from app.db.base import Base
from app.models.enums import (
    CellRunStatus,
    ExamStatus,
    ExportVariant,
    IngestStatus,
    Level,
    MatrixStatus,
    QuestionType,
    UserRole,
)

TABLES = Base.metadata.tables

ERD_TABLES = {
    "schools", "users", "refresh_tokens", "subjects",
    "sample_exams",
    "exam_matrices", "matrix_cells", "matrix_conversions",
    "exams", "exam_cell_runs", "exam_questions", "exam_exports",
    "exam_bank_entries",
}  # fmt: skip

TENANT_TABLES = {"users", "sample_exams", "exam_matrices", "exams", "exam_bank_entries"}


def columns(table: str) -> set[str]:
    return set(TABLES[table].columns.keys())


def enum_values(table: str, column: str) -> set[str]:
    col_type = TABLES[table].columns[column].type
    assert isinstance(col_type, Enum)
    return set(col_type.enums)


def fk(table: str, column: str):
    [key] = TABLES[table].columns[column].foreign_keys
    return key


def unique_sets(table: str) -> list[set[str]]:
    sets = [
        {col.name for col in c.columns}
        for c in TABLES[table].constraints
        if isinstance(c, UniqueConstraint)
    ]
    sets += [{col.name} for col in TABLES[table].columns if col.unique]
    return sets


def checks(table: str) -> str:
    return " ".join(
        str(c.sqltext) for c in TABLES[table].constraints if isinstance(c, CheckConstraint)
    )


def test_all_erd_tables_exist():
    assert set(TABLES) == ERD_TABLES


@pytest.mark.parametrize("table", sorted(ERD_TABLES))
def test_ddl_compiles_for_postgresql(table):
    CreateTable(TABLES[table]).compile(dialect=postgresql.dialect())


def test_mappers_and_relationships_configure():
    from sqlalchemy.orm import configure_mappers

    configure_mappers()


# ----- Multi-tenant -----


@pytest.mark.parametrize("table", sorted(TENANT_TABLES))
def test_business_tables_belong_to_a_school(table):
    col = TABLES[table].columns["school_id"]
    assert not col.nullable
    assert col.index
    assert fk(table, "school_id").target_fullname == "schools.id"


# Đo bằng EXPLAIN ANALYZE trên ~885k câu / 590k ô: thiếu index thì nạp câu của một đề
# mất ~90 ms (seq scan), có index ~0,02 ms. Các trang này được polling mỗi 2 giây.
# Index đơn là đủ: index ghép (cột lọc, cột sắp) không nhanh hơn vì mỗi truy vấn chỉ
# trả vài chục dòng, mà to gấp ~4 lần (index đơn được B-tree deduplication).
HOT_LOOKUP_COLUMNS = [
    ("matrix_cells", "matrix_id"),  # chi tiết ma trận
    ("exam_questions", "exam_id"),  # chi tiết đề, xuất DOCX
    ("exam_matrices", "owner_id"),  # danh sách ma trận của GV
    ("exams", "owner_id"),  # danh sách đề của GV
]


@pytest.mark.parametrize(("table", "column"), HOT_LOOKUP_COLUMNS)
def test_hot_lookup_columns_are_indexed(table, column):
    assert TABLES[table].columns[column].index


@pytest.mark.parametrize("table", ["exams", "exam_matrices", "sample_exams"])
def test_status_not_indexed_since_no_query_filters_on_it(table):
    assert not TABLES[table].columns["status"].index


def test_user_has_only_teacher_and_admin_roles():
    assert enum_values("users", "role") == {r.value for r in UserRole} == {"teacher", "admin"}


# ----- Đề mẫu (admin) -----


def test_sample_exam_tracks_rag_ingest():
    assert enum_values("sample_exams", "status") == {s.value for s in IngestStatus}
    assert {"uploaded_by", "storage_key", "rag_job_id", "error_message"} <= columns("sample_exams")


def test_sample_exam_not_uploaded_twice_in_same_school():
    assert {"school_id", "checksum_sha256"} in unique_sets("sample_exams")


# ----- Ma trận -----


def test_matrix_keeps_source_file_and_marker_markdown():
    assert {"source_storage_key", "source_mime_type", "markdown", "parse_issues", "confirmed_at"} <= columns("exam_matrices")
    assert enum_values("exam_matrices", "status") == {s.value for s in MatrixStatus}


def test_matrix_subject_and_grade_unknown_until_parsed():
    t = TABLES["exam_matrices"]
    assert t.columns["subject_id"].nullable and t.columns["grade"].nullable
    assert "grade BETWEEN 10 AND 12" in checks("exam_matrices")


def test_matrix_cell_keeps_text_topic_unit_and_competencies():
    assert {"topic", "content_unit", "question_type", "level", "statement_levels", "question_count", "competency_codes", "sort_order"} <= columns("matrix_cells")
    assert TABLES["matrix_cells"].columns["content_unit"].nullable  # ô gộp cả chủ đề
    assert enum_values("matrix_cells", "question_type") == {t.value for t in QuestionType}
    assert enum_values("matrix_cells", "level") == {lv.value for lv in Level}
    assert "question_count > 0" in checks("matrix_cells")


def test_matrix_cells_deleted_with_matrix():
    assert fk("matrix_cells", "matrix_id").ondelete == "CASCADE"


# ----- Đề -----


def test_exam_status_and_source_matrix():
    assert enum_values("exams", "status") == {s.value for s in ExamStatus}
    assert fk("exams", "matrix_id").target_fullname == "exam_matrices.id"
    assert {"title", "duration_minutes", "cells_done", "cells_total"} <= columns("exams")


def test_exam_cell_run_tracks_short_and_error_cells():
    assert enum_values("exam_cell_runs", "status") == {s.value for s in CellRunStatus}
    assert {"exam_id", "matrix_cell_id", "valid_count", "rejected_count", "error_message"} <= columns("exam_cell_runs")


def test_exam_question_keeps_rag_json_source_cell_and_order():
    assert {"exam_id", "matrix_cell_id", "content", "position", "original"} <= columns("exam_questions")
    assert TABLES["exam_questions"].columns["original"].nullable  # null = GV chưa sửa
    assert isinstance(TABLES["exam_questions"].columns["content"].type, postgresql.JSONB)


def test_exam_exported_as_student_and_teacher_docx():
    assert enum_values("exam_exports", "variant") == {v.value for v in ExportVariant} == {"student", "teacher"}
    assert enum_values("exam_exports", "format") == {"docx"}


@pytest.mark.parametrize("table", ["exam_cell_runs", "exam_questions", "exam_exports", "exam_bank_entries"])
def test_exam_children_deleted_with_exam(table):
    assert fk(table, "exam_id").ondelete == "CASCADE"


# ----- Ngân hàng đề -----


def test_exam_enters_school_bank_once():
    assert {"exam_id"} in unique_sets("exam_bank_entries")
    assert {"saved_by", "saved_at"} <= columns("exam_bank_entries")


def test_bank_entry_has_visibility_flag_and_rag_ingest_tracking():
    assert {"is_visible", "rag_status", "rag_job_id", "error_message"} <= columns("exam_bank_entries")
    assert TABLES["exam_bank_entries"].columns["is_visible"].default.arg is False  # mặc định tạm ẩn
    assert enum_values("exam_bank_entries", "rag_status") == {s.value for s in IngestStatus}
