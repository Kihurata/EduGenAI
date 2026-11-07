"""Giáo viên duyệt đề (F-05): sửa, xoá, sinh lại từng câu, bù ô thiếu, duyệt.

Đầu ra mong muốn:
- Câu sửa được kiểm lại bằng cùng bộ kiểm cấu trúc với câu RAG trả (đúng dạng, đúng mức của ô)
  rồi qua RAG /validate; sai thì 422 kèm lý do, câu cũ giữ nguyên. RAG không phản hồi → 503.
- Câu sửa giữ trích dẫn cũ, bỏ kết quả SymPy cũ; bản RAG gốc được giữ ở lần sửa đầu.
- Xoá câu: ô thành thiếu, đề incomplete. Không tự bù.
- Sinh lại một câu: job nền gọi RAG với đúng ô đó, count = 1; câu mới thay vào đúng vị trí.
  RAG lỗi thì câu cũ giữ nguyên, lỗi ghi vào ô.
- Bù ô thiếu: job nền sinh đúng số câu còn thiếu, câu xếp lại theo thứ tự ô.
- Duyệt: chỉ khi mọi ô đủ câu, không thì 409 kèm danh sách ô thiếu. Đề đã duyệt không sửa được.
- Sinh lại gặp lỗi bất ngờ (không phải LLMError): đề không kẹt `generating`, câu cũ giữ nguyên, ô ghi lỗi chung.
- Chỉ người tạo đề hoặc admin được duyệt. Đề đang sinh thì chưa thao tác được.
"""

import copy
import uuid

import pytest
from sqlalchemy import update

from app.api.v1 import exams as exams_api
from app.core.errors import LLMError
from app.models import Exam
from app.models.enums import ExamStatus
from app.services.exam_jobs import GENERIC_ERROR
from tests.api.test_exams import BASE, generated_exam


def url(exam: dict, *path) -> str:
    return "/".join([BASE, exam["id"], *map(str, path)])


def fetch(client, headers, exam: dict) -> dict:
    return client.get(url(exam), headers=headers).json()


def edit(client, headers, exam, question, **changes):
    content = copy.deepcopy(question["content"]) | changes
    return client.put(url(exam, "questions", question["id"]), json=content, headers=headers)


def part(exam: dict, name: str) -> list[dict]:
    return [q for q in exam["questions"] if q["part"] == name]


def test_TC_010_teacher_edits_deletes_and_regenerates_a_question(client, teacher_headers, rag, monkeypatch):
    exam = generated_exam(client, teacher_headers)
    first, second = exam["questions"][:2]
    short = part(exam, "III")[0]

    resp = edit(client, teacher_headers, exam, first, stem="Cho tập $A = \\{1; 2\\}$. Chọn khẳng định đúng.")
    assert resp.status_code == 200, resp.text
    assert resp.json()["content"]["stem"] == "Cho tập $A = \\{1; 2\\}$. Chọn khẳng định đúng."
    assert resp.json()["edited"] is True

    resp = edit(client, teacher_headers, exam, short, answer="12,345")
    assert resp.status_code == 422
    assert resp.json()["detail"] == ["Đáp án trả lời ngắn tối đa 4 ký tự (đang là '12,345')"]

    assert client.delete(url(exam, "questions", second["id"]), headers=teacher_headers).status_code == 200
    after = fetch(client, teacher_headers, exam)
    assert after["status"] == "incomplete"
    [run] = [r for r in after["cell_runs"] if r["matrix_cell_id"] == second["matrix_cell_id"]]
    assert (run["status"], run["valid_count"], run["question_count"]) == ("short", 1, 2)

    generate = rag.generate
    calls = []

    def fresh(cell):
        calls.append(cell)
        valid, rejected = generate(cell)
        for q in valid:
            q["de_bai"] = "Câu sinh lại"
        return valid, rejected

    monkeypatch.setattr(rag, "generate", fresh)
    target = exam["questions"][5]
    resp = client.post(url(exam, "questions", target["id"], "regenerate"), headers=teacher_headers)
    assert resp.status_code == 202
    [call] = calls
    assert call.count == 1
    assert call.type.value == target["content"]["type"]
    after = fetch(client, teacher_headers, exam)
    [new] = [q for q in after["questions"] if q["id"] == target["id"]]
    assert (new["position"], new["matrix_cell_id"]) == (target["position"] - 1, target["matrix_cell_id"])
    assert new["content"]["stem"] == "Câu sinh lại"
    assert new["edited"] is False


def test_edit_keeps_citations_drops_sympy_and_keeps_first_original(client, teacher_headers, db):
    exam = generated_exam(client, teacher_headers)
    question = part(exam, "III")[0]
    original = question["content"]
    edit(client, teacher_headers, exam, question, citations=["bịa"], check={"ok": True}, answer="7,1")
    edited = edit(client, teacher_headers, exam, question, answer="7,2").json()["content"]
    assert edited["answer"] == "7,2"
    assert edited["citations"] == original["citations"]
    assert edited["check"] is None
    row = db.get(Exam, uuid.UUID(exam["id"])).questions[question["position"] - 1]
    db.refresh(row)
    assert row.original == original


def test_edit_must_match_cell_type_and_level(client, teacher_headers):
    exam = generated_exam(client, teacher_headers)
    question = exam["questions"][0]
    resp = edit(client, teacher_headers, exam, question, level="Vận dụng")
    assert resp.status_code == 422
    assert resp.json()["detail"] == ["Sai mức độ: ô cần Biết, RAG trả Vận dụng"]
    resp = edit(client, teacher_headers, exam, question, options=["1", "2"])
    assert resp.json()["detail"] == ["Câu nhiều lựa chọn cần đúng 4 phương án không rỗng"]


def test_rag_validation_errors_and_outage(client, teacher_headers, rag, monkeypatch):
    exam = generated_exam(client, teacher_headers)
    question = exam["questions"][0]
    monkeypatch.setattr(rag, "validate", lambda q, cell: ["SymPy: đáp án không khớp"])
    resp = edit(client, teacher_headers, exam, question, answer="C")
    assert (resp.status_code, resp.json()["detail"]) == (422, ["SymPy: đáp án không khớp"])

    def down(q, cell):
        raise LLMError("RAG service quá thời gian phản hồi")

    monkeypatch.setattr(rag, "validate", down)
    resp = edit(client, teacher_headers, exam, question, answer="C")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Chưa kiểm được câu sửa: RAG service quá thời gian phản hồi"
    assert fetch(client, teacher_headers, exam)["questions"][0]["content"] == question["content"]


def test_failed_regeneration_keeps_question_and_records_error(client, teacher_headers, rag, monkeypatch):
    exam = generated_exam(client, teacher_headers)
    question = exam["questions"][0]

    def fail(cell):
        raise LLMError("model quá tải")

    monkeypatch.setattr(rag, "generate", fail)
    assert client.post(url(exam, "questions", question["id"], "regenerate"), headers=teacher_headers).status_code == 202
    after = fetch(client, teacher_headers, exam)
    assert after["status"] == "generated"
    assert after["questions"][0]["content"] == question["content"]
    [run] = [r for r in after["cell_runs"] if r["matrix_cell_id"] == question["matrix_cell_id"]]
    assert run["error_message"] == "model quá tải"


def test_unexpected_regeneration_error_does_not_leave_exam_generating(client, teacher_headers, rag, monkeypatch):
    exam = generated_exam(client, teacher_headers)
    question = exam["questions"][0]

    def crash(cell):
        raise RuntimeError("lỗi bất ngờ")

    monkeypatch.setattr(rag, "generate", crash)
    assert client.post(url(exam, "questions", question["id"], "regenerate"), headers=teacher_headers).status_code == 202
    after = fetch(client, teacher_headers, exam)
    assert after["status"] == "generated"  # không kẹt generating, vẫn sửa/duyệt được
    assert after["questions"][0]["content"] == question["content"]
    [run] = [r for r in after["cell_runs"] if r["matrix_cell_id"] == question["matrix_cell_id"]]
    assert run["error_message"] == GENERIC_ERROR
    assert client.post(url(exam, "approve"), headers=teacher_headers).status_code == 200


def test_fill_missing_cell_then_approve(client, teacher_headers, rag, monkeypatch):
    generate = rag.generate
    monkeypatch.setattr(rag, "generate", lambda cell: ([], []) if cell.id == 1 else generate(cell))
    exam = generated_exam(client, teacher_headers)
    assert exam["status"] == "incomplete"
    assert len(exam["questions"]) == 20
    cell_id = exam["cell_runs"][0]["matrix_cell_id"]

    resp = client.post(url(exam, "approve"), headers=teacher_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"] == ["Ô 1 (Phần I, Mệnh đề và tập hợp – Mệnh đề, Biết): thiếu 2 câu"]

    monkeypatch.setattr(rag, "generate", generate)
    assert client.post(url(exam, "cells", cell_id, "fill"), headers=teacher_headers).status_code == 202
    after = fetch(client, teacher_headers, exam)
    assert after["status"] == "generated"
    assert [q["position"] for q in after["questions"]] == list(range(1, 23))
    assert {q["matrix_cell_id"] for q in after["questions"][:2]} == {cell_id}
    resp = client.post(url(exam, "cells", cell_id, "fill"), headers=teacher_headers)
    assert (resp.status_code, resp.json()["detail"]) == (409, "Ô này đã đủ câu")

    resp = client.post(url(exam, "approve"), headers=teacher_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_fill_asks_again_until_cell_is_full_when_rag_returns_fewer(client, teacher_headers, rag, monkeypatch):
    generate = rag.generate
    monkeypatch.setattr(rag, "generate", lambda cell: ([], []) if cell.id == 1 else generate(cell))
    exam = generated_exam(client, teacher_headers)
    cell_id = exam["cell_runs"][0]["matrix_cell_id"]

    def one_at_a_time(cell):
        valid, rejected = generate(cell)
        return valid[:1], rejected

    monkeypatch.setattr(rag, "generate", one_at_a_time)
    assert client.post(url(exam, "cells", cell_id, "fill"), headers=teacher_headers).status_code == 202
    after = fetch(client, teacher_headers, exam)
    assert len(after["questions"]) == 22
    assert after["status"] == "generated"


def test_fill_loses_the_race_to_a_concurrent_claim(client, teacher_headers, monkeypatch):
    exam = generated_exam(client, teacher_headers)
    cell_id = exam["cell_runs"][0]["matrix_cell_id"]
    client.delete(url(exam, "questions", exam["questions"][0]["id"]), headers=teacher_headers)
    real = exams_api.get_reviewable

    def reviewable_then_other_request_claims(db, exam_id, user):
        found = real(db, exam_id, user)  # đề vẫn chưa generating ở request này
        db.execute(update(Exam).where(Exam.id == exam_id).values(status=ExamStatus.generating))
        db.commit()  # request kia claim xong trước
        return found

    monkeypatch.setattr(exams_api, "get_reviewable", reviewable_then_other_request_claims)
    resp = client.post(url(exam, "cells", cell_id, "fill"), headers=teacher_headers)
    assert (resp.status_code, resp.json()["detail"]) == (409, "Đề đang sinh, chờ xong rồi thao tác")


def test_approved_exam_is_locked(client, teacher_headers):
    exam = generated_exam(client, teacher_headers)
    assert client.post(url(exam, "approve"), headers=teacher_headers).status_code == 200
    question = exam["questions"][0]
    for resp in (
        edit(client, teacher_headers, exam, question, answer="C"),
        client.delete(url(exam, "questions", question["id"]), headers=teacher_headers),
        client.post(url(exam, "questions", question["id"], "regenerate"), headers=teacher_headers),
        client.post(url(exam, "approve"), headers=teacher_headers),
    ):
        assert (resp.status_code, resp.json()["detail"]) == (409, "Đề đã duyệt, không sửa được")


def test_generating_exam_is_locked(client, teacher_headers, db):
    exam = generated_exam(client, teacher_headers)
    row = db.get(Exam, uuid.UUID(exam["id"]))
    row.status = ExamStatus.generating
    db.commit()
    resp = client.post(url(exam, "approve"), headers=teacher_headers)
    assert (resp.status_code, resp.json()["detail"]) == (409, "Đề đang sinh, chờ xong rồi thao tác")


def test_only_owner_or_admin_reviews(client, teacher_headers, colleague_headers, admin_headers):
    exam = generated_exam(client, teacher_headers)
    question = exam["questions"][0]
    assert client.delete(url(exam, "questions", question["id"]), headers=colleague_headers).status_code == 404
    assert client.delete(url(exam, "questions", uuid.uuid4()), headers=teacher_headers).status_code == 404
    assert client.post(url(exam, "approve"), headers=admin_headers).status_code == 200


# ----- BUG-003: approval needs every generated short answer verified by SymPy -----


def _short_answer_with(db, exam, check, original=None):
    from app.models import ExamQuestion

    first = next(q for q in exam["questions"] if q["content"]["type"] == "short_answer")
    row = db.get(ExamQuestion, uuid.UUID(first["id"]))
    row.content = {**row.content, "check": check}
    row.original = original
    db.commit()
    return first["position"]


@pytest.mark.parametrize("check", [
    {"expr": "sqrt(2)", "verified": False},  # SymPy disagrees or could not compute it
    {"expr": "21", "verified": True},  # e81f6617 Q20: the expr only restates the answer
    None,  # never checked
])
def test_BUG_003_unverified_short_answer_blocks_approval(client, teacher_headers, db, check):
    exam = generated_exam(client, teacher_headers)
    position = _short_answer_with(db, exam, check)

    resp = client.post(url(exam, "approve"), headers=teacher_headers)

    assert resp.status_code == 409
    assert resp.json()["detail"] == [f"Câu {position} (Phần III): đáp án chưa được SymPy kiểm từ dữ kiện của đề"]


def test_BUG_003_short_answer_the_teacher_edited_does_not_block_approval(client, teacher_headers, db):
    """An edit drops the old SymPy result on purpose; the teacher has taken responsibility for the answer."""
    exam = generated_exam(client, teacher_headers)
    _short_answer_with(db, exam, None, original={"type": "short_answer"})

    assert client.post(url(exam, "approve"), headers=teacher_headers).status_code == 200


# ----- BUG-005: regenerating or filling sees the exam's other questions -----


def _capture(rag, monkeypatch):
    generate, calls = rag.generate, []

    def capturing(cell):
        calls.append(cell)
        return generate(cell)

    monkeypatch.setattr(rag, "generate", capturing)
    return calls


def test_BUG_005_regenerating_a_question_sends_the_stems_of_the_whole_exam(client, teacher_headers, rag, monkeypatch):
    exam = generated_exam(client, teacher_headers)
    calls = _capture(rag, monkeypatch)

    client.post(url(exam, "questions", exam["questions"][5]["id"], "regenerate"), headers=teacher_headers)

    assert calls[0].previous_stems == tuple(q["content"]["stem"] for q in exam["questions"])


def test_BUG_005_filling_a_cell_sends_the_stems_already_in_the_exam(client, teacher_headers, rag, monkeypatch):
    generate = rag.generate
    monkeypatch.setattr(rag, "generate", lambda cell: ([], []) if cell.id == 1 else generate(cell))
    exam = generated_exam(client, teacher_headers)
    monkeypatch.setattr(rag, "generate", generate)
    calls = _capture(rag, monkeypatch)

    client.post(url(exam, "cells", exam["cell_runs"][0]["matrix_cell_id"], "fill"), headers=teacher_headers)

    assert calls[0].previous_stems == tuple(q["content"]["stem"] for q in exam["questions"])
