"""Tóm tắt: mã chủ đề Lý và Hóa (D-013, T-050): mỗi mã là một chương SGK Kết nối tri thức, phần đầu mã RAG là mã môn
(`ly/vat_li_nhiet`). Chương trên ma trận chỉ khớp chủ đề của đúng môn đó; chương lớp thấp hơn dùng được cho ma trận lớp
cao hơn, không ngược lại; mỗi mã có cụm từ tìm kiếm cho RAG.
"""

import pytest

from app.domain.cell import Cell
from app.domain.matrix_json import build_matrix_json
from app.domain.matrix_reader import ParsedCell, ParsedMatrix
from app.domain.topics import TOPICS, find_topic, topics_for
from app.models.enums import Level, QuestionType
from app.rag.vocab import TOPIC_QUERIES
from app.services.rag_client import to_rag_cell

MC = QuestionType.multiple_choice


@pytest.mark.parametrize("name, subject, code", [
    ("Vật lí nhiệt", "ly", "vat_li_nhiet"),
    ("Vật lí hạt nhân và phóng xạ", "ly", "vat_li_hat_nhan"),
    ("Ester – Lipid", "hoa", "ester_lipid"),
    ("Nguyên tố nhóm IA và nhóm IIA", "hoa", "nhom_ia_iia"),
])
def test_chapter_name_resolves_to_its_subject_topic(name, subject, code):
    topic = find_topic(name, grade=12, subject=subject)
    assert (topic.code, topic.strand, topic.subject) == (code, subject, subject)


def test_chapter_of_another_subject_does_not_match():
    assert find_topic("Vật lí nhiệt", grade=12, subject="toan") is None
    assert find_topic("Nguyên hàm và tích phân", grade=12, subject="ly") is None


def test_lower_grade_chapter_fits_higher_grade_matrix_but_not_the_reverse():
    assert find_topic("Động học", grade=12, subject="ly").code == "dong_hoc"
    assert find_topic("Vật lí nhiệt", grade=10, subject="ly") is None


def test_topic_lists_per_subject():
    assert len(topics_for("ly")) == 15
    assert len(topics_for("hoa")) == 23
    assert len(topics_for("toan")) == 25
    assert all(t.subject == "toan" for t in topics_for("toan"))


@pytest.mark.parametrize("topic", sorted(t.code for t in TOPICS.values() if t.subject in ("ly", "hoa")))
def test_every_physics_and_chemistry_topic_has_a_search_phrase(topic):
    t = TOPICS[topic]
    assert TOPIC_QUERIES.get(f"{t.strand}/{t.code}")


def test_physics_matrix_cells_get_physics_topic_codes():
    parsed = ParsedMatrix(subject="ly", grade=12, name="Thi thử",
                          cells=[ParsedCell(MC, "Vật lí nhiệt", None, Level.biet, 18)])
    result = build_matrix_json(parsed)
    assert result.rag_cells[0]["topic"] == "vat_li_nhiet"
    assert not any("chưa có mã" in i.message for i in result.issues)


def test_unknown_physics_chapter_issue_names_the_subject_list():
    parsed = ParsedMatrix(subject="ly", grade=12, name="Thi thử",
                          cells=[ParsedCell(MC, "Quang học", None, Level.biet, 18)])
    [issue] = [i for i in build_matrix_json(parsed).issues if "Quang học" in i.message]
    assert "Toán" not in issue.message


def test_physics_cell_is_sent_to_rag_with_subject_prefixed_topic():
    cell = Cell(id=1, subject="ly", grade=12, topic="Vật lí nhiệt", content_unit=None, type=MC,
                level=Level.biet, count=2)
    rag_cell = to_rag_cell(cell)
    assert (rag_cell["subject"], rag_cell["topic"], rag_cell["grade"]) == ("ly", "ly/vat_li_nhiet", 12)
