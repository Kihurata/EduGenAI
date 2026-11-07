"""Đề đã duyệt (câu lưu trong DB) → JSON đề app.rag cắt được."""

import json
import uuid
from datetime import datetime
from types import SimpleNamespace as NS

from app.domain.topics import TOPICS
from app.rag.chunking import chunk_file
from app.services.bank import exam_to_rag_json

MC = {"type": "multiple_choice", "level": "Biết", "stem": "MC1", "options": ["a", "b", "c", "d"], "answer": "C",
      "figure": "Hình tròn", "table": [["x", "y"], ["1", "2"]]}  # fmt: skip
TF = {"type": "true_false", "level": "Hiểu", "stem": "TF1", "answer": "ĐSĐS",
      "statements": [{"text": t, "correct": c} for t, c in zip("wxyz", (True, False, True, False))]}  # fmt: skip
SA = {"type": "short_answer", "level": "Vận dụng", "stem": "SA1", "answer": "7,5"}
TOPIC = "Nguyên hàm và tích phân"


def exam(*contents, grade=12, topic=TOPIC):
    matrix = NS(subject=NS(code="toan"), grade=grade)
    qs = [NS(content=c, matrix_cell=NS(topic=topic, matrix=matrix)) for c in contents]
    return NS(id=uuid.uuid4(), title="Đề thử", created_at=datetime(2026, 5, 1), questions=qs,
              matrix=matrix)  # fmt: skip


def test_three_parts_are_numbered_per_part():
    out = json.loads(exam_to_rag_json(exam(MC, TF, SA, MC)))
    assert [(q["part"], q["cau"]) for q in out["questions"]] == [("I", 1), ("II", 1), ("III", 1), ("I", 2)]
    assert out["official"] is True and out["subject"] == "toan"
    assert out["questions"][0]["topic"] == "dai_so_giai_tich/nguyen_ham_tich_phan"


def test_grade_10_bank_question_uses_grade_10_topic_code():
    out = json.loads(exam_to_rag_json(exam(MC, grade=10, topic=TOPICS["ham_so_bac_hai"].name)))
    assert out["questions"][0]["topic"] == "dai_so_giai_tich/ham_so_bac_hai"


def test_true_false_statements_carry_their_answers():
    q = json.loads(exam_to_rag_json(exam(TF)))["questions"][0]
    assert [(s["label"], s["answer"]) for s in q["statements"]] == [("a", True), ("b", False), ("c", True), ("d", False)]
    assert "answer" not in q


def test_options_figure_and_table_are_carried_over():
    q = json.loads(exam_to_rag_json(exam(MC)))["questions"][0]
    assert q["options"] == {"A": "a", "B": "b", "C": "c", "D": "d"} and q["answer"] == "C"
    assert q["figure"] == "Hình tròn" and q["table"] == [["x", "y"], ["1", "2"]]


def test_short_answer_and_chunker_accepts_the_result(tmp_path):
    path = tmp_path / "e.json"
    path.write_bytes(exam_to_rag_json(exam(MC, TF, SA)))
    chunks = chunk_file(path)
    assert [c.part for c in chunks] == ["I", "II", "III"]
    assert "Đáp án: 7,5" in chunks[2].text
    assert "Hình: Hình tròn" in chunks[0].text and "| x | y |" in chunks[0].text
