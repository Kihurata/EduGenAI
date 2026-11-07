"""Ngân hàng ĐỀ của trường: đề chính thức đã được tổ chuyên môn thống nhất.

Đầu ra mong muốn:
- Chỉ admin nạp đề vào ngân hàng: đề đã duyệt (approved) trong trường, mỗi đề một lần.
- Đề nạp vào được gửi sang RAG học (bản GV có đáp án, lời giải) và theo dõi trạng thái ingest.
- Cờ hiển thị do admin bật/tắt, mặc định tạm ẩn: GV chỉ thấy, mở, tải đề đã bật cờ.
- Chỉ admin được sửa/xóa. Trường khác không thấy. Đề lưu kèm ma trận gốc.
"""

import json

from app.core.errors import LLMError
from app.rag.chunking import chunk_file
from tests.api.conftest import login
from tests.api.test_exams import approved_exam, generated_exam

BASE = "/api/v1/bank"


def added(client, teacher_headers, admin_headers, **body) -> dict:
    exam = approved_exam(client, teacher_headers)
    resp = client.post(BASE, json={"exam_id": exam["id"], **body}, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_admin_adds_exam_hidden_by_default_and_sends_to_rag(
    client, teacher_headers, admin_headers, rag, tmp_path, school
):
    entry = added(client, teacher_headers, admin_headers)
    assert (entry["title"], entry["grade"], entry["subject"]) == ("KTGK - HK1 - 10", 12, "Toán học")
    assert entry["is_visible"] is False
    assert entry["saved_by"]["full_name"] == "Quản trị ND"
    [sent] = rag.ingested
    exam = json.loads(sent["data"])  # đề đã duyệt gửi dạng JSON mà app.rag cắt được, không phải DOCX
    assert sent["filename"] == f"exam_bank-{entry['exam_id']}.json"
    assert sent["meta"] == {
        "source": "exam_bank", "subject": "toan", "grade": 12, "title": "KTGK - HK1 - 10",
        "exam_id": entry["exam_id"], "school_id": str(school.id),
    }  # fmt: skip  — RBAC: đề ngân hàng chỉ trường mình truy xuất được (T-024)
    assert [q["part"] for q in exam["questions"]] == ["I"] * 12 + ["II"] * 4 + ["III"] * 6
    assert [q["cau"] for q in exam["questions"]][12:16] == [1, 2, 3, 4]  # đánh số lại theo phần
    path = tmp_path / sent["filename"]
    path.write_bytes(sent["data"])
    chunks = chunk_file(path)  # đúng định dạng RAG đang cắt
    assert len(chunks) == 22
    assert "Đáp án:" in chunks[0].text and chunks[0].exam_code

    rag.job_status = "processing"
    assert client.get(f"{BASE}/{entry['id']}", headers=admin_headers).json()["rag_status"] == "sent"
    rag.job_status = "done"
    assert client.get(f"{BASE}/{entry['id']}", headers=admin_headers).json()["rag_status"] == "ingested"


def test_rag_error_is_recorded(client, teacher_headers, admin_headers, rag):
    rag.ingest_error = LLMError("RAG service trả lỗi 500")
    entry = added(client, teacher_headers, admin_headers)
    detail = client.get(f"{BASE}/{entry['id']}", headers=admin_headers).json()
    assert detail["rag_status"] == "failed"
    assert "500" in detail["error_message"]


def test_teacher_cannot_add_edit_or_delete(client, teacher_headers, admin_headers):
    exam = approved_exam(client, teacher_headers)
    resp = client.post(BASE, json={"exam_id": exam["id"]}, headers=teacher_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Chỉ admin được dùng chức năng này"
    entry = added(client, teacher_headers, admin_headers, is_visible=True)
    url = f"{BASE}/{entry['id']}"
    assert client.patch(url, json={"title": "Của tôi"}, headers=teacher_headers).status_code == 403
    assert client.delete(url, headers=teacher_headers).status_code == 403


def test_hidden_entry_is_invisible_to_teachers(client, teacher_headers, colleague_headers, admin_headers):
    entry = added(client, teacher_headers, admin_headers)
    url = f"{BASE}/{entry['id']}"
    assert client.get(BASE, headers=colleague_headers).json() == []
    assert client.get(url, headers=colleague_headers).status_code == 404
    assert client.get(f"{url}/export", params={"variant": "student"}, headers=colleague_headers).status_code == 404
    assert client.get(f"/api/v1/exams/{entry['exam_id']}", headers=colleague_headers).status_code == 404
    assert [e["id"] for e in client.get(BASE, headers=admin_headers).json()] == [entry["id"]]


def test_admin_shows_entry_then_colleagues_view_and_download(
    client, teacher_headers, colleague_headers, admin_headers
):
    entry = added(client, teacher_headers, admin_headers)
    url = f"{BASE}/{entry['id']}"
    resp = client.patch(url, json={"is_visible": True}, headers=admin_headers)
    assert resp.json()["is_visible"] is True

    assert [e["id"] for e in client.get(BASE, headers=colleague_headers).json()] == [entry["id"]]
    detail = client.get(url, headers=colleague_headers).json()
    assert len(detail["exam"]["questions"]) == 22
    assert len(detail["matrix"]["cells"]) == 18  # lưu kèm ma trận gốc
    resp = client.get(f"{url}/export", params={"variant": "teacher"}, headers=colleague_headers)
    assert resp.status_code == 200 and resp.content[:2] == b"PK"
    assert client.get(f"/api/v1/exams/{entry['exam_id']}", headers=colleague_headers).status_code == 200

    client.patch(url, json={"is_visible": False}, headers=admin_headers)  # tạm ẩn lại
    assert client.get(BASE, headers=colleague_headers).json() == []


def test_admin_edits_and_removes_entry(client, teacher_headers, admin_headers):
    entry = added(client, teacher_headers, admin_headers)
    url = f"{BASE}/{entry['id']}"
    resp = client.patch(url, json={"title": "Giữa kì 1 – Toán 10", "duration_minutes": 60}, headers=admin_headers)
    assert (resp.json()["title"], resp.json()["duration_minutes"]) == ("Giữa kì 1 – Toán 10", 60)
    assert client.delete(url, headers=admin_headers).status_code == 204
    assert client.get(BASE, headers=admin_headers).json() == []
    assert client.get(f"/api/v1/exams/{entry['exam_id']}", headers=teacher_headers).status_code == 200  # đề vẫn còn


def test_TC_012_admin_banks_approved_exam(client, teacher_headers, colleague_headers, admin_headers, rag):
    exam = approved_exam(client, teacher_headers)
    resp = client.post(BASE, json={"exam_id": exam["id"]}, headers=admin_headers)
    assert resp.status_code == 201
    assert resp.json()["is_visible"] is False
    resp = client.post(BASE, json={"exam_id": exam["id"]}, headers=admin_headers)
    assert (resp.status_code, resp.json()["detail"]) == (409, "Đề đã có trong ngân hàng")
    [sent] = rag.ingested
    assert sent["meta"]["source"] == "exam_bank"

    entry = client.get(BASE, headers=admin_headers).json()[0]
    client.patch(f"{BASE}/{entry['id']}", json={"is_visible": True}, headers=admin_headers)
    assert [e["id"] for e in client.get(BASE, params={"grade": 12}, headers=colleague_headers).json()] == [entry["id"]]
    resp = client.get(f"{BASE}/{entry['id']}/export", params={"variant": "student"}, headers=colleague_headers)
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"


def test_only_approved_exam_of_own_school_once(client, teacher_headers, admin_headers, outsider_headers):
    exam = approved_exam(client, teacher_headers)
    other_admin = login(client, "admin@lqd.vn")
    assert client.post(BASE, json={"exam_id": exam["id"]}, headers=other_admin).status_code == 404
    assert client.post(BASE, json={"exam_id": exam["id"]}, headers=admin_headers).status_code == 201
    resp = client.post(BASE, json={"exam_id": exam["id"]}, headers=admin_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Đề đã có trong ngân hàng"

    draft = generated_exam(client, teacher_headers)
    resp = client.post(BASE, json={"exam_id": draft["id"]}, headers=admin_headers)
    assert (resp.status_code, resp.json()["detail"]) == (409, "Chỉ nạp được đề đã duyệt")


def test_other_school_cannot_see_bank(client, teacher_headers, admin_headers, outsider_headers):
    entry = added(client, teacher_headers, admin_headers, is_visible=True)
    assert client.get(BASE, headers=outsider_headers).json() == []
    assert client.get(f"{BASE}/{entry['id']}", headers=outsider_headers).status_code == 404


def test_list_filters_by_grade(client, teacher_headers, admin_headers):
    added(client, teacher_headers, admin_headers, is_visible=True)
    assert len(client.get(BASE, params={"grade": 12}, headers=teacher_headers).json()) == 1
    assert client.get(BASE, params={"grade": 11}, headers=teacher_headers).json() == []


def test_admin_lists_every_exam_of_school_to_choose_from(client, teacher_headers, colleague_headers, admin_headers):
    mine = generated_exam(client, teacher_headers)
    assert client.get("/api/v1/exams", headers=colleague_headers).json() == []
    assert [e["id"] for e in client.get("/api/v1/exams", headers=admin_headers).json()] == [mine["id"]]


def test_unexpected_error_in_background_task_ends_failed_not_pending(client, teacher_headers, admin_headers, rag):
    rag.ingest_error = RuntimeError("hết bộ nhớ")  # không phải LLMError
    entry = added(client, teacher_headers, admin_headers)
    detail = client.get(f"{BASE}/{entry['id']}", headers=admin_headers).json()
    assert detail["rag_status"] == "failed"
    assert "hết bộ nhớ" not in detail["error_message"]
    assert detail["error_message"].startswith("Lỗi hệ thống")


def test_error_building_the_exam_json_ends_failed(client, teacher_headers, admin_headers, monkeypatch):
    from app.services import bank

    def boom(exam):
        raise KeyError("stem")

    monkeypatch.setattr(bank, "exam_to_rag_json", boom)
    entry = added(client, teacher_headers, admin_headers)
    detail = client.get(f"{BASE}/{entry['id']}", headers=admin_headers).json()
    assert detail["rag_status"] == "failed"
    assert detail["error_message"].startswith("Lỗi hệ thống")
    assert "stem" not in detail["error_message"]


def test_entry_deleted_before_task_runs_is_ignored(session_factory, rag, storage):
    import uuid

    from app.services.bank import send_exam_to_rag

    send_exam_to_rag(session_factory, uuid.uuid4(), rag, storage)  # không văng lỗi
    assert rag.ingested == []
