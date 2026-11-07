"""Đề mẫu (T-050): admin tải đề (PDF/DOCX/JSON) → BE lưu file gốc → LLM đọc thành bản nháp JSON →
GV duyệt, sửa đề bài/đáp án/metadata → xác nhận thì mới gửi RAG học → theo dõi trạng thái.

Đầu ra mong muốn:
- Tải lên trả 201 (pending); job nền đọc đề → needs_review kèm bản nháp và lỗi kiểm tra; đọc lỗi → failed.
- Môn chọn trên form; môn, official (luôn false) và school_id do hệ thống gắn, không lấy từ bản nháp.
- Sửa bản nháp thì kiểm tra lại; còn lỗi thì không xác nhận được (422).
- Xác nhận → sent; RAG xong → ingested. Sửa sau khi đã nạp → needs_review, xác nhận lại thì nạp lại cùng tên file.
- GV tải và duyệt đề của mình; RAG nhận teacher_id để chỉ GV đó truy xuất. GV khác và đề admin tải → 404 với GV;
  admin thấy mọi đề trong trường, đề admin tải không có teacher_id (cả trường dùng).
- Chỉ PDF/DOCX/JSON; cùng một file không tải hai lần trong một trường; trường khác → 404.
"""

import json

from app.core.errors import LLMError
from app.services.draft_extractor import ExtractionError

BASE = "/api/v1/admin/sample-exams"
PDF = "application/pdf"


def upload(client, headers, data=b"%PDF-1.7 de mau", name="de_01.pdf", mime=PDF, grade="12", subject="ly"):
    return client.post(
        BASE, files={"file": (name, data, mime)},
        data={"grade": grade, "title": "Đề số 01", "subject": subject}, headers=headers,
    )  # fmt: skip


def fixed_draft(client, headers, sample_id):
    """Gán chủ đề cho câu còn thiếu (lỗi duy nhất của bản nháp mẫu) rồi lưu."""
    draft = client.get(f"{BASE}/{sample_id}", headers=headers).json()["draft"]
    draft["questions"][1]["topic"] = "ly/vat_li_nhiet"
    return client.put(f"{BASE}/{sample_id}/draft", json={"draft": draft}, headers=headers)


def test_upload_reads_a_draft_for_review_without_sending_to_rag(client, admin_headers, rag, storage, extractor):
    resp = upload(client, admin_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "pending"
    detail = client.get(f"{BASE}/{resp.json()['id']}", headers=admin_headers).json()
    assert detail["status"] == "needs_review"
    assert (detail["subject"], detail["grade"]) == ("ly", 12)
    assert extractor.calls[0]["subject"] == "ly" and extractor.calls[0]["data"] == b"%PDF-1.7 de mau"
    draft = detail["draft"]
    assert (draft["subject"], draft["official"], draft["grade"]) == ("ly", False, 12)  # system fields win
    assert [(i["question"], "chủ đề" in i["message"]) for i in detail["issues"]] == [("III-1", True)]
    assert rag.ingested == []  # nothing reaches RAG before the teacher confirms
    assert storage.path(detail["storage_key"]).read_bytes() == b"%PDF-1.7 de mau"


def test_confirm_with_issues_is_rejected(client, admin_headers, rag):
    sample_id = upload(client, admin_headers).json()["id"]
    resp = client.post(f"{BASE}/{sample_id}/confirm", headers=admin_headers)
    assert resp.status_code == 422
    assert rag.ingested == []


def test_teacher_edits_metadata_then_confirms_and_rag_learns_it(client, admin_headers, rag, school):
    sample_id = upload(client, admin_headers).json()["id"]
    draft = client.get(f"{BASE}/{sample_id}", headers=admin_headers).json()["draft"]
    draft["questions"][1]["topic"] = "ly/vat_li_nhiet"
    draft["questions"][0]["level"] = "Hiểu"
    draft["exam_kind"] = "tot_nghiep"  # D-017 (T-055, TC-028)
    draft["subject"], draft["official"] = "toan", True  # ignored: the system sets these
    saved = client.put(f"{BASE}/{sample_id}/draft", json={"draft": draft}, headers=admin_headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["issues"] == []
    assert (saved.json()["draft"]["subject"], saved.json()["draft"]["official"]) == ("ly", False)

    rag.job_status = "processing"
    confirmed = client.post(f"{BASE}/{sample_id}/confirm", headers=admin_headers)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "sent"
    [sent] = rag.ingested
    assert sent["filename"] == f"sample-{sample_id}.json"
    body = json.loads(sent["data"])
    assert body["questions"][0]["level"] == "Hiểu"
    assert sent["meta"] == {
        "source": "sample_exam", "subject": "ly", "grade": 12, "title": "Đề số 01",
        "school_id": str(school.id), "official": False, "exam_kind": "tot_nghiep",
    }  # fmt: skip
    rag.job_status = "done"
    assert client.get(f"{BASE}/{sample_id}", headers=admin_headers).json()["status"] == "ingested"


def test_editing_after_ingest_needs_a_new_confirm_that_reingests_the_same_file(client, admin_headers, rag):
    sample_id = upload(client, admin_headers).json()["id"]
    fixed_draft(client, admin_headers, sample_id)
    client.post(f"{BASE}/{sample_id}/confirm", headers=admin_headers)
    assert client.get(f"{BASE}/{sample_id}", headers=admin_headers).json()["status"] == "ingested"

    resp = fixed_draft(client, admin_headers, sample_id)
    assert resp.json()["status"] == "needs_review"
    client.post(f"{BASE}/{sample_id}/confirm", headers=admin_headers)
    assert [s["filename"] for s in rag.ingested] == [f"sample-{sample_id}.json"] * 2


def test_grade_edited_in_draft_is_used(client, admin_headers, rag):
    sample_id = upload(client, admin_headers).json()["id"]
    draft = client.get(f"{BASE}/{sample_id}", headers=admin_headers).json()["draft"]
    draft["questions"][1]["topic"] = "ly/vat_li_nhiet"
    draft["grade"] = 11  # grade-12 chapters no longer fit
    issues = client.put(f"{BASE}/{sample_id}/draft", json={"draft": draft}, headers=admin_headers).json()["issues"]
    assert any("chủ đề" in i["message"] for i in issues)
    draft["questions"] = [q | {"topic": "ly/dao_dong"} for q in draft["questions"]]
    saved = client.put(f"{BASE}/{sample_id}/draft", json={"draft": draft}, headers=admin_headers).json()
    assert (saved["issues"], saved["grade"]) == ([], 11)
    client.post(f"{BASE}/{sample_id}/confirm", headers=admin_headers)
    assert rag.ingested[0]["meta"]["grade"] == 11


def test_extraction_error_marks_failed(client, admin_headers, extractor):
    extractor.error = ExtractionError("LLM không đọc được file")
    sample_id = upload(client, admin_headers).json()["id"]
    detail = client.get(f"{BASE}/{sample_id}", headers=admin_headers).json()
    assert detail["status"] == "failed"
    assert "LLM không đọc được file" in detail["error_message"]
    assert detail["draft"] is None


def test_unexpected_storage_error_marks_failed(client, admin_headers, storage, monkeypatch):
    def broken_read(key):
        raise RuntimeError("ổ đĩa mất kết nối")

    monkeypatch.setattr(storage, "read", broken_read)
    sample_id = upload(client, admin_headers).json()["id"]
    detail = client.get(f"{BASE}/{sample_id}", headers=admin_headers).json()
    assert detail["status"] == "failed"
    assert "ổ đĩa mất kết nối" not in detail["error_message"]
    assert detail["error_message"].startswith("Lỗi hệ thống")


def test_rag_error_on_confirm_marks_failed_and_can_be_retried(client, admin_headers, rag):
    sample_id = upload(client, admin_headers).json()["id"]
    fixed_draft(client, admin_headers, sample_id)
    rag.ingest_error = LLMError("RAG service trả lỗi 500")
    detail = client.post(f"{BASE}/{sample_id}/confirm", headers=admin_headers).json()
    assert detail["status"] == "failed" and "500" in detail["error_message"]
    rag.ingest_error = None
    assert client.post(f"{BASE}/{sample_id}/confirm", headers=admin_headers).json()["status"] in ("sent", "ingested")


def test_rag_reports_failed_ingest(client, admin_headers, rag):
    rag.job_status = "failed"
    sample_id = upload(client, admin_headers).json()["id"]
    fixed_draft(client, admin_headers, sample_id)
    client.post(f"{BASE}/{sample_id}/confirm", headers=admin_headers)
    assert client.get(f"{BASE}/{sample_id}", headers=admin_headers).json()["status"] == "failed"


def test_cannot_edit_or_confirm_before_a_draft_exists(client, admin_headers, extractor):
    extractor.error = ExtractionError("hỏng")
    sample_id = upload(client, admin_headers).json()["id"]
    assert client.post(f"{BASE}/{sample_id}/confirm", headers=admin_headers).status_code == 409
    assert client.put(f"{BASE}/{sample_id}/draft", json={"draft": {}}, headers=admin_headers).status_code == 409


def test_validation(client, admin_headers):
    assert upload(client, admin_headers, name="a.png", mime="image/png").status_code == 415
    assert upload(client, admin_headers, grade="9").status_code == 422
    assert upload(client, admin_headers, subject="van").status_code == 422
    assert upload(client, admin_headers, b'{"questions": []}', "de.json", "application/json").status_code == 201
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert upload(client, admin_headers, b"PK docx", "de.docx", docx_mime).status_code == 201
    resp = upload(client, admin_headers, b"PK docx", "de_copy.docx", docx_mime)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "File này đã được tải lên trước đó"


def test_other_school_cannot_see(client, admin_headers, outsider_admin_headers):
    sample_id = upload(client, admin_headers).json()["id"]
    assert client.get(BASE, headers=outsider_admin_headers).json() == []
    assert client.get(f"{BASE}/{sample_id}", headers=outsider_admin_headers).status_code == 404
    assert client.put(f"{BASE}/{sample_id}/draft", json={"draft": {}}, headers=outsider_admin_headers).status_code == 404
    assert client.post(f"{BASE}/{sample_id}/confirm", headers=outsider_admin_headers).status_code == 404


def test_topics_of_a_subject_for_the_review_dropdown(client, admin_headers):
    topics = client.get("/api/v1/topics", params={"subject": "ly"}, headers=admin_headers).json()
    assert len(topics) == 15
    assert topics[-1] == {"code": "ly/vat_li_hat_nhan", "name": "Vật lí hạt nhân và phóng xạ", "grade": 12}
    assert client.get("/api/v1/topics", params={"subject": "van"}, headers=admin_headers).status_code == 422


def test_teacher_uploads_own_sample_exam_and_rag_learns_it_for_that_teacher_only(client, teacher, teacher_headers, rag):
    sample_id = upload(client, teacher_headers, name="gv.pdf", data=b"%PDF gv").json()["id"]
    assert fixed_draft(client, teacher_headers, sample_id).status_code == 200
    confirmed = client.post(f"{BASE}/{sample_id}/confirm", headers=teacher_headers)
    assert confirmed.status_code == 200, confirmed.text
    [sent] = rag.ingested
    assert sent["meta"]["teacher_id"] == str(teacher.id)
    assert sent["meta"]["school_id"] == str(teacher.school_id)


def test_a_teacher_sees_only_own_sample_exams_admin_sees_all(client, admin_headers, teacher_headers, colleague_headers):
    mine = upload(client, teacher_headers, name="gv1.pdf", data=b"%PDF gv1").json()["id"]
    school_wide = upload(client, admin_headers).json()["id"]

    assert [s["id"] for s in client.get(BASE, headers=teacher_headers).json()] == [mine]
    assert client.get(BASE, headers=colleague_headers).json() == []
    assert {s["id"] for s in client.get(BASE, headers=admin_headers).json()} == {mine, school_wide}
    for sample_id in (mine, school_wide):  # a colleague's upload and the admin's are not the teacher's to edit
        assert client.get(f"{BASE}/{sample_id}", headers=colleague_headers).status_code == 404
        assert client.put(f"{BASE}/{sample_id}/draft", json={"draft": {}}, headers=colleague_headers).status_code == 404
        assert client.post(f"{BASE}/{sample_id}/confirm", headers=colleague_headers).status_code == 404
    assert client.get(f"{BASE}/{mine}", headers=admin_headers).status_code == 200


def test_T040_empty_upload_is_refused_and_nothing_is_stored(client, admin_headers, rag, storage, extractor):
    """T-040 edge case: an empty file is a clear 400, never reaches the extractor, storage or RAG."""
    r = upload(client, admin_headers, data=b"")

    assert r.status_code == 400
    assert not client.get(BASE, headers=admin_headers).json()
    assert not rag.ingested
