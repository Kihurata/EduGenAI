"""Job nền xử lý ma trận: uploaded → converting → parsed | invalid | failed.

Đầu ra mong muốn:
- Trong lúc marker chạy, ma trận ở trạng thái converting (frontend hỏi lại thấy được).
- Parse được và khớp hàng tổng → parsed, lưu markdown, môn/lớp/tên và các ô theo thứ tự.
- Có lỗi parse/lệch tổng, hoặc môn chưa có trong hệ thống → invalid, lưu parse_issues.
- Marker lỗi → failed kèm error_message; không ném lỗi ra ngoài job.
"""

import uuid
from pathlib import Path

from app.domain.matrix_reader import read_matrix
from app.models import ExamMatrix, School, Subject, User
from app.models.enums import Level, MatrixStatus, QuestionType
from app.services.exam_jobs import run_exam_generation
from app.services.matrix_converter import ConversionError
from app.services.matrix_jobs import process_matrix, update_cells
from app.services.sample_exams import extract_draft
from app.services.storage import LocalStorage

FIXTURE = Path(__file__).parents[1] / "fixtures" / "matrices" / "ktgk_hk1_toan10.md"


class FakeConverter:
    def __init__(self, session_factory, markdown=None, error=None):
        self.session_factory, self.markdown, self.error = session_factory, markdown, error
        self.seen_status = None
        self.paths = []

    def convert(self, source: Path) -> str:
        self.paths.append(source)
        with self.session_factory() as s:
            self.seen_status = s.query(ExamMatrix).one().status
        if self.error:
            raise self.error
        return self.markdown


def setup(db, tmp_path, with_subject=True) -> tuple[ExamMatrix, LocalStorage]:
    school = School(code="nd", name="THPT Nguyễn Du")
    db.add(school)
    if with_subject:
        db.add(Subject(code="toan", name="Toán học"))
    db.flush()
    teacher = User(school_id=school.id, email="gv@nd.vn", password_hash="x", full_name="GV")
    db.add(teacher)
    db.flush()
    storage = LocalStorage(tmp_path)
    storage.save("matrices/m1/source.png", b"png")
    matrix = ExamMatrix(
        school_id=school.id, owner_id=teacher.id, source_filename="mt.png",
        source_mime_type="image/png", source_storage_key="matrices/m1/source.png",
    )  # fmt: skip
    db.add(matrix)
    db.commit()
    return matrix, storage


def reload(session_factory, matrix_id) -> ExamMatrix:
    with session_factory() as s:
        m = s.get(ExamMatrix, matrix_id)
        _ = m.cells, m.subject
        return m


def test_real_matrix_is_parsed(db, session_factory, tmp_path):
    matrix, storage = setup(db, tmp_path)
    conv = FakeConverter(session_factory, FIXTURE.read_text(encoding="utf-8"))
    process_matrix(session_factory, matrix.id, conv, storage)
    m = reload(session_factory, matrix.id)
    assert conv.seen_status == MatrixStatus.converting
    assert conv.paths == [tmp_path / "matrices" / "m1" / "source.png"]
    assert m.status == MatrixStatus.parsed
    assert (m.subject.code, m.grade, m.name) == ("toan", 10, "KTGK - HK1 - 10")
    assert m.markdown.startswith(FIXTURE.read_text(encoding="utf-8")[:20])
    assert m.parse_issues == []
    assert [c.sort_order for c in m.cells] == list(range(1, 19))
    first, tf = m.cells[0], m.cells[10]
    assert (first.topic, first.content_unit, first.question_type, first.level) == (
        "Mệnh đề và tập hợp", "Mệnh đề", QuestionType.multiple_choice, Level.biet,
    )  # fmt: skip
    assert (first.question_count, first.competency_codes) == (2, ["TD1.2"])
    assert tf.content_unit is None
    assert tf.statement_levels == ["Biết", "Biết", "Hiểu", "Hiểu"]


def test_matrix_with_issues_is_invalid(db, session_factory, tmp_path):
    matrix, storage = setup(db, tmp_path)
    process_matrix(session_factory, matrix.id, FakeConverter(session_factory, "không có bảng"), storage)
    m = reload(session_factory, matrix.id)
    assert m.status == MatrixStatus.invalid
    assert any("bảng HTML" in i["message"] for i in m.parse_issues)
    assert m.cells == []


def test_subject_missing_from_catalog_is_an_issue(db, session_factory, tmp_path):
    matrix, storage = setup(db, tmp_path, with_subject=False)
    conv = FakeConverter(session_factory, FIXTURE.read_text(encoding="utf-8"))
    process_matrix(session_factory, matrix.id, conv, storage)
    m = reload(session_factory, matrix.id)
    assert m.status == MatrixStatus.invalid
    assert any("chưa có trong hệ thống" in i["message"] for i in m.parse_issues)


def test_editing_cells_of_a_matrix_without_subject_is_an_issue(db, session_factory, tmp_path):
    matrix, storage = setup(db, tmp_path, with_subject=False)
    process_matrix(session_factory, matrix.id, FakeConverter(session_factory, FIXTURE.read_text(encoding="utf-8")), storage)
    with session_factory() as s:
        m = s.get(ExamMatrix, matrix.id)
        update_cells(s, m, read_matrix(FIXTURE.read_text(encoding="utf-8")).cells)
        messages = [i["message"] for i in m.parse_issues]
    assert any("Chưa có môn" in msg for msg in messages)
    assert not any("toan" in msg for msg in messages)  # no silent fallback to Toán


def test_converter_failure_marks_matrix_failed(db, session_factory, tmp_path):
    matrix, storage = setup(db, tmp_path)
    conv = FakeConverter(session_factory, error=ConversionError("marker quá thời gian"))
    process_matrix(session_factory, matrix.id, conv, storage)
    m = reload(session_factory, matrix.id)
    assert m.status == MatrixStatus.failed
    assert "marker quá thời gian" in m.error_message


def test_unexpected_converter_error_marks_matrix_failed(db, session_factory, tmp_path):
    matrix, storage = setup(db, tmp_path)
    conv = FakeConverter(session_factory, error=RuntimeError("không đọc được ảnh"))
    process_matrix(session_factory, matrix.id, conv, storage)
    m = reload(session_factory, matrix.id)
    assert m.status == MatrixStatus.failed
    assert "không đọc được ảnh" not in m.error_message
    assert m.error_message.startswith("Lỗi hệ thống")


def test_deleted_background_job_rows_do_not_crash(session_factory):
    missing_id = uuid.uuid4()
    extract_draft(session_factory, missing_id, None, None)
    process_matrix(session_factory, missing_id, None, None)
    run_exam_generation(session_factory, missing_id, None)


def test_reprocessing_replaces_old_cells(db, session_factory, tmp_path):
    matrix, storage = setup(db, tmp_path)
    conv = FakeConverter(session_factory, FIXTURE.read_text(encoding="utf-8"))
    process_matrix(session_factory, matrix.id, conv, storage)
    process_matrix(session_factory, matrix.id, conv, storage)
    assert len(reload(session_factory, matrix.id).cells) == 18


def test_TC_020_gemini_json_matrix_is_parsed_and_edits_are_rechecked(db, session_factory, tmp_path):
    """T-054: kết quả JSON của Gemini đi qua cùng job; GV sửa ô thì vẫn kiểm lại 12/4/6 và tổng 10 điểm."""
    mid_term = (Path(__file__).parents[1] / "fixtures" / "matrix_extract" / "giua_ki_toan12.json").read_text("utf-8")
    matrix, storage = setup(db, tmp_path)
    process_matrix(session_factory, matrix.id, FakeConverter(session_factory, mid_term), storage)
    m = reload(session_factory, matrix.id)
    assert (m.status, m.grade, m.parse_issues) == (MatrixStatus.parsed, 12, [])
    assert sum(c.question_count for c in m.cells if c.question_type == QuestionType.true_false) == 4

    with session_factory() as s:
        edited = s.get(ExamMatrix, matrix.id)
        cells = [c for c in read_matrix(edited.markdown).cells if c.type != QuestionType.short_answer]  # bỏ Phần III
        update_cells(s, edited, cells)
        s.commit()
    assert reload(session_factory, matrix.id).status == MatrixStatus.invalid


def test_TC_020_saving_valid_gemini_json_cells_keeps_matrix_parsed(db, session_factory, tmp_path):
    """JSON không có hàng 'Tổng số câu' dạng bảng: lưu ô hợp lệ không được sinh lỗi thiếu hàng tổng."""
    mid_term = (Path(__file__).parents[1] / "fixtures" / "matrix_extract" / "giua_ki_toan12.json").read_text("utf-8")
    matrix, storage = setup(db, tmp_path)
    process_matrix(session_factory, matrix.id, FakeConverter(session_factory, mid_term), storage)
    with session_factory() as s:
        m = s.get(ExamMatrix, matrix.id)
        update_cells(s, m, read_matrix(m.markdown).cells)
        s.commit()
    m = reload(session_factory, matrix.id)
    assert not any("Tổng số" in i["message"] for i in m.parse_issues)
    assert (m.status, m.parse_issues) == (MatrixStatus.parsed, [])
