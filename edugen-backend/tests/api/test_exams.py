"""Sinh đề từ ma trận đã xác nhận (job nền, RAG giả lập) và xuất DOCX bản HS/GV.

Đầu ra mong muốn:
- Chỉ sinh đề từ ma trận confirmed; trả 202 + exam_id, job nền gọi RAG từng ô.
- Đủ câu mọi ô → generated; có ô lỗi/thiếu → incomplete; không ô nào có câu → failed.
- Câu xếp Phần I → II → III theo thứ tự ô; tiến độ cells_done/cells_total.
- Chỉ xuất DOCX đề đã duyệt (F-05). Xuất: tên trường, tên kỳ thi, thời gian GV nhập; bản GV có bảng đáp án. Lưu file + bản ghi.
"""

import io

from docx import Document
from sqlalchemy import select

from app.core.errors import LLMError
from app.models import ExamExport
from tests.api.test_matrices import uploaded

BASE = "/api/v1/exams"


def confirmed_matrix(client, headers) -> dict:
    m = uploaded(client, headers)
    cells = [{k: c[k] for k in ("topic", "content_unit", "type", "level", "count", "statement_levels", "competency_codes")} for c in m["cells"]]
    assert client.put(f"/api/v1/matrices/{m['id']}/cells", json={"cells": cells, "grade": 12}, headers=headers).status_code == 200
    assert client.post(f"/api/v1/matrices/{m['id']}/confirm", headers=headers).status_code == 200
    return m


def create_exam(client, headers, matrix_id, **extra):
    return client.post(BASE, json={"matrix_id": matrix_id, "duration_minutes": 45, **extra}, headers=headers)


def generated_exam(client, headers) -> dict:
    m = confirmed_matrix(client, headers)
    resp = create_exam(client, headers, m["id"])
    assert resp.status_code == 202, resp.text
    return client.get(f"{BASE}/{resp.json()['id']}", headers=headers).json()


def approved_exam(client, headers) -> dict:
    exam = generated_exam(client, headers)
    resp = client.post(f"{BASE}/{exam['id']}/approve", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_generates_every_cell_in_matrix_order(client, teacher_headers):
    exam = generated_exam(client, teacher_headers)
    assert exam["status"] == "generated"
    assert (exam["title"], exam["duration_minutes"]) == ("KTGK - HK1 - 10", 45)
    assert exam["cells_done"] == exam["cells_total"] == 18
    assert [r["status"] for r in exam["cell_runs"]] == ["complete"] * 18
    assert [r["sort_order"] for r in exam["cell_runs"]] == list(range(1, 19))
    questions = exam["questions"]
    assert len(questions) == 22  # 12 nhiều lựa chọn + 4 đúng sai + 6 trả lời ngắn
    assert [q["position"] for q in questions] == list(range(1, 23))
    assert [q["part"] for q in questions] == ["I"] * 12 + ["II"] * 4 + ["III"] * 6
    assert questions[0]["content"]["type"] == "multiple_choice"
    assert questions[12]["content"]["statements"][0]["text"]


def test_custom_title(client, teacher_headers):
    m = confirmed_matrix(client, teacher_headers)
    exam_id = create_exam(client, teacher_headers, m["id"], title="Kiểm tra giữa kì").json()["id"]
    assert client.get(f"{BASE}/{exam_id}", headers=teacher_headers).json()["title"] == "Kiểm tra giữa kì"


def test_matrix_must_be_confirmed_and_owned(client, teacher_headers, colleague_headers):
    m = uploaded(client, teacher_headers)
    resp = create_exam(client, teacher_headers, m["id"])
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Ma trận chưa được xác nhận"
    assert create_exam(client, colleague_headers, m["id"]).status_code == 404


def test_cell_error_makes_exam_incomplete(client, teacher_headers, rag, monkeypatch):
    generate = rag.generate

    def flaky(cell):
        if cell.type.value == "true_false":
            raise LLMError("model quá tải")
        return generate(cell)

    monkeypatch.setattr(rag, "generate", flaky)
    exam = generated_exam(client, teacher_headers)
    assert exam["status"] == "incomplete"
    errors = [r for r in exam["cell_runs"] if r["status"] == "error"]
    assert len(errors) == 3 and errors[0]["error_message"] == "model quá tải"
    assert len(exam["questions"]) == 18


def test_unexpected_generation_error_marks_exam_failed(client, teacher_headers, rag, monkeypatch):
    def broken_generate(cell):
        raise RuntimeError("RAG trả dữ liệu hỏng")

    monkeypatch.setattr(rag, "generate", broken_generate)
    exam = generated_exam(client, teacher_headers)
    assert exam["status"] == "failed"
    assert len(exam["cell_runs"]) == exam["cells_total"]
    assert {r["status"] for r in exam["cell_runs"]} == {"error"}
    assert all("RAG trả dữ liệu hỏng" not in r["error_message"] for r in exam["cell_runs"])
    assert all(r["error_message"].startswith("Lỗi hệ thống") for r in exam["cell_runs"])


def test_unexpected_error_in_one_cell_keeps_other_cells(client, teacher_headers, rag, monkeypatch):
    generate = rag.generate

    def flaky(cell):
        if cell.type.value == "true_false":
            raise RuntimeError("RAG trả dữ liệu hỏng")
        return generate(cell)

    monkeypatch.setattr(rag, "generate", flaky)
    exam = generated_exam(client, teacher_headers)
    assert exam["status"] == "incomplete"
    errors = [r for r in exam["cell_runs"] if r["status"] == "error"]
    assert len(errors) == 3
    assert all("RAG trả dữ liệu hỏng" not in r["error_message"] for r in errors)
    assert len(exam["questions"]) == 18


def test_nothing_generated_is_failed(client, teacher_headers, rag, monkeypatch):
    monkeypatch.setattr(rag, "generate", lambda cell: ([], []))
    exam = generated_exam(client, teacher_headers)
    assert exam["status"] == "failed"
    assert {r["status"] for r in exam["cell_runs"]} == {"short"}


def test_colleague_cannot_see_exam_not_in_bank(client, teacher_headers, colleague_headers, outsider_headers):
    exam = generated_exam(client, teacher_headers)
    assert client.get(f"{BASE}/{exam['id']}", headers=colleague_headers).status_code == 404
    assert client.get(f"{BASE}/{exam['id']}", headers=outsider_headers).status_code == 404


def docx(resp) -> tuple[list[str], int]:
    doc = Document(io.BytesIO(resp.content))
    return [p.text for p in doc.paragraphs], len(doc.tables)


def test_export_student_and_teacher_docx(client, teacher_headers, db, storage):
    exam = approved_exam(client, teacher_headers)
    resp = client.get(f"{BASE}/{exam['id']}/export", params={"variant": "student"}, headers=teacher_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "attachment" in resp.headers["content-disposition"]
    paragraphs, tables = docx(resp)
    assert paragraphs[0] == "THPT NGUYỄN DU"
    assert "KTGK - HK1 - 10" in paragraphs
    assert "Môn: Toán học – Lớp 12" in paragraphs
    assert "Thời gian làm bài: 45 phút (không kể thời gian phát đề)" in paragraphs
    assert tables == 0

    resp = client.get(f"{BASE}/{exam['id']}/export", params={"variant": "teacher"}, headers=teacher_headers)
    paragraphs, tables = docx(resp)
    assert "ĐÁP ÁN VÀ LỜI GIẢI" in paragraphs and tables == 4  # 3 bảng đáp án + ma trận đề

    exports = db.scalars(select(ExamExport).order_by(ExamExport.created_at)).all()
    assert [e.variant.value for e in exports] == ["student", "teacher"]
    assert storage.read(exports[1].storage_key) == resp.content


def test_only_approved_exam_is_exported(client, teacher_headers):
    exam = generated_exam(client, teacher_headers)
    resp = client.get(f"{BASE}/{exam['id']}/export", params={"variant": "student"}, headers=teacher_headers)
    assert (resp.status_code, resp.json()["detail"]) == (409, "Đề chưa được duyệt, chưa xuất được")
