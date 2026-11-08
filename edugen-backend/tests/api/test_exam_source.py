"""Nguồn dữ liệu sinh đề và nơi đề duyệt xong được đưa tới.

Đầu ra mong muốn:
- GV chọn nguồn khi sinh đề: school (mặc định) hoặc personal. Nguồn cá nhân gửi teacher_id cho RAG (thấy thêm đề
  mẫu GV tự tải); nguồn trường không gửi.
- Đề nguồn trường duyệt xong tự vào hàng chờ admin xét (review_status = pending); admin nạp ngân hàng → accepted,
  từ chối → rejected kèm lý do, gỡ khỏi ngân hàng → về pending.
- Đề nguồn cá nhân duyệt xong ở lại bộ sưu tập của GV: admin không thấy, không nạp ngân hàng được.
- GV đổi tên, xoá đề của mình; không đụng được đề đã là đề chính thức hay đề của người khác.
"""

from tests.api.test_exams import BASE, confirmed_matrix, create_exam


def exam_with(client, headers, source: str | None = None, approve: bool = True) -> dict:
    m = confirmed_matrix(client, headers)
    resp = create_exam(client, headers, m["id"], **({"source": source} if source else {}))
    assert resp.status_code == 202, resp.text
    exam_id = resp.json()["id"]
    if approve:
        resp = client.post(f"{BASE}/{exam_id}/approve", headers=headers)
        assert resp.status_code == 200, resp.text
        return resp.json()
    return client.get(f"{BASE}/{exam_id}", headers=headers).json()


def record_cells(rag, monkeypatch) -> list:
    cells = []
    original = rag.generate

    def generate(cell):
        cells.append(cell)
        return original(cell)

    monkeypatch.setattr(rag, "generate", generate)
    return cells


def test_school_source_is_default_and_hides_teacher_uploads_from_rag(client, teacher_headers, teacher, rag, monkeypatch):
    cells = record_cells(rag, monkeypatch)
    exam = exam_with(client, teacher_headers, approve=False)
    assert exam["source"] == "school"
    assert cells and all(c.teacher_id is None and c.school_id for c in cells)


def test_personal_source_sends_teacher_id(client, teacher_headers, teacher, rag, monkeypatch):
    cells = record_cells(rag, monkeypatch)
    exam = exam_with(client, teacher_headers, "personal", approve=False)
    assert exam["source"] == "personal"
    assert cells and all(c.teacher_id == str(teacher.id) for c in cells)


def test_school_exam_goes_to_admin_queue_on_approval(client, teacher_headers, admin_headers):
    draft = exam_with(client, teacher_headers, approve=False)
    assert draft["review_status"] is None  # chưa duyệt thì chưa tới lượt admin xét
    exam = client.post(f"{BASE}/{draft['id']}/approve", headers=teacher_headers).json()
    assert exam["review_status"] == "pending"
    listed = client.get(BASE, headers=admin_headers).json()
    assert [e["id"] for e in listed] == [exam["id"]]

    entry = client.post("/api/v1/bank", json={"exam_id": exam["id"]}, headers=admin_headers).json()
    assert client.get(f"{BASE}/{exam['id']}", headers=teacher_headers).json()["review_status"] == "accepted"
    assert client.delete(f"/api/v1/bank/{entry['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"{BASE}/{exam['id']}", headers=teacher_headers).json()["review_status"] == "pending"


def test_admin_rejects_with_note(client, teacher_headers, admin_headers):
    exam = exam_with(client, teacher_headers)
    resp = client.post("/api/v1/bank/reject", json={"exam_id": exam["id"], "note": " Trùng đề năm ngoái "}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    mine = client.get(f"{BASE}/{exam['id']}", headers=teacher_headers).json()
    assert (mine["review_status"], mine["review_note"]) == ("rejected", "Trùng đề năm ngoái")
    # đã từ chối vẫn chọn lại được
    assert client.post("/api/v1/bank", json={"exam_id": exam["id"]}, headers=admin_headers).status_code == 201
    assert client.post("/api/v1/bank/reject", json={"exam_id": exam["id"]}, headers=admin_headers).status_code == 409


def test_teacher_cannot_reject(client, teacher_headers):
    exam = exam_with(client, teacher_headers)
    assert client.post("/api/v1/bank/reject", json={"exam_id": exam["id"]}, headers=teacher_headers).status_code == 403


def test_personal_exam_stays_private(client, teacher_headers, admin_headers):
    exam = exam_with(client, teacher_headers, "personal")
    assert exam["status"] == "approved" and exam["review_status"] is None
    assert client.get(BASE, headers=admin_headers).json() == []
    assert client.post("/api/v1/bank", json={"exam_id": exam["id"]}, headers=admin_headers).status_code == 404
    assert client.post("/api/v1/bank/reject", json={"exam_id": exam["id"]}, headers=admin_headers).status_code == 404


def test_teacher_filters_own_exams_by_source(client, teacher_headers):
    school = exam_with(client, teacher_headers)
    personal = exam_with(client, teacher_headers, "personal")
    assert [e["id"] for e in client.get(BASE, params={"source": "personal"}, headers=teacher_headers).json()] == [personal["id"]]
    assert [e["id"] for e in client.get(BASE, params={"source": "school"}, headers=teacher_headers).json()] == [school["id"]]
    assert len(client.get(BASE, headers=teacher_headers).json()) == 2


def test_teacher_renames_and_deletes_own_exam(client, teacher_headers, colleague_headers):
    exam = exam_with(client, teacher_headers, "personal")
    assert client.patch(f"{BASE}/{exam['id']}", json={"title": "x"}, headers=colleague_headers).status_code == 404
    resp = client.patch(f"{BASE}/{exam['id']}", json={"title": "  Đề ôn chương 1 "}, headers=teacher_headers)
    assert resp.status_code == 200 and resp.json()["title"] == "Đề ôn chương 1"
    assert client.delete(f"{BASE}/{exam['id']}", headers=colleague_headers).status_code == 404
    assert client.delete(f"{BASE}/{exam['id']}", headers=teacher_headers).status_code == 204
    assert client.get(f"{BASE}/{exam['id']}", headers=teacher_headers).status_code == 404


def test_official_exam_cannot_be_renamed_or_deleted_by_teacher(client, teacher_headers, admin_headers):
    exam = exam_with(client, teacher_headers)
    assert client.post("/api/v1/bank", json={"exam_id": exam["id"]}, headers=admin_headers).status_code == 201
    assert client.patch(f"{BASE}/{exam['id']}", json={"title": "x"}, headers=teacher_headers).status_code == 409
    assert client.delete(f"{BASE}/{exam['id']}", headers=teacher_headers).status_code == 409
