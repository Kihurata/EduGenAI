"""Hợp đồng giá trị enum với RAG (payload ô) và với tiêu đề cột của ma trận."""

from app.models.enums import LEVEL_ORDER, ExamStatus, Level, MatrixStatus, QuestionType


def test_question_type_values_match_rag_cell_contract():
    assert {t.value for t in QuestionType} == {"multiple_choice", "true_false", "short_answer"}


def test_level_values_match_matrix_column_headers():
    assert [lv.value for lv in Level] == ["Biết", "Hiểu", "Vận dụng"]


def test_levels_are_ordered_from_recall_to_application():
    assert sorted([Level.van_dung, Level.biet, Level.hieu], key=LEVEL_ORDER.index) == [
        Level.biet,
        Level.hieu,
        Level.van_dung,
    ]


def test_matrix_status_values():
    assert {s.value for s in MatrixStatus} == {
        "uploaded", "converting", "parsed", "invalid", "confirmed", "failed",
    }  # fmt: skip


def test_exam_status_values():
    assert {s.value for s in ExamStatus} == {"generating", "generated", "incomplete", "failed", "approved"}
