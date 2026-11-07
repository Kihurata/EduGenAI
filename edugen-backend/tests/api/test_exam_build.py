"""TC-009 (nghiệm thu F-02, chạy với RAG giả lập nên ở mức integration): ma trận Toán → đề 22 câu qua API.

Đầu ra mong muốn:
- Đề có 22 câu: Phần I Câu 1–12, Phần II Câu 1–4, Phần III Câu 1–6 (đếm trên file DOCX xuất ra).
- Mọi câu qua kiểm tra câu hỏi (`parse_question`) với đúng ô của nó.
- Mọi câu đúng môn, dạng câu và mức độ của ô ma trận chứa nó.
"""

import re
import uuid

from app.domain.question import parse_question, to_rag
from app.models import ExamMatrix
from app.services.exam_jobs import cell_of
from tests.api.test_exams import BASE, approved_exam, docx

PART_RE = re.compile(r"^PHẦN (I{1,3})\.")
QUESTION_RE = re.compile(r"^Câu (\d+)\.")


def numbers_by_part(paragraphs: list[str]) -> dict[str, list[int]]:
    """Số "Câu n." trong phần đề (trước bảng đáp án), gom theo PHẦN."""
    parts: dict[str, list[int]] = {}
    current = None
    for text in paragraphs:
        if m := PART_RE.match(text):
            current = parts.setdefault(m[1], [])
        elif (m := QUESTION_RE.match(text)) and current is not None:
            current.append(int(m[1]))
    return parts


def test_TC_009_build_toan_exam_from_matrix(client, teacher_headers, db):
    exam = approved_exam(client, teacher_headers)
    matrix = db.get(ExamMatrix, uuid.UUID(exam["matrix_id"]))
    rows = {c.id: c for c in matrix.cells}

    assert matrix.subject.code == "toan"
    assert len(exam["questions"]) == 22
    for q in exam["questions"]:
        cell = cell_of(matrix, rows[uuid.UUID(q["matrix_cell_id"])])
        assert parse_question(to_rag(q["content"]), cell)[1] == [], q["position"]
        assert q["content"]["type"] == cell.type.value
        assert q["content"]["level"] == cell.level.value
        assert q["part"] == cell.part
        assert cell.school_id == str(matrix.school_id)  # RBAC: retrieval sees this school's sample exams

    resp = client.get(f"{BASE}/{exam['id']}/export", params={"variant": "student"}, headers=teacher_headers)
    assert resp.status_code == 200, resp.text
    paragraphs, _ = docx(resp)
    assert numbers_by_part(paragraphs) == {
        "I": list(range(1, 13)),
        "II": list(range(1, 5)),
        "III": list(range(1, 7)),
    }
