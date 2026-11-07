"""Cấu trúc đề tốt nghiệp THPT theo QĐ 764/2024 (chính thức)."""

from decimal import Decimal

import pytest

from app.domain.exam_structure import TYPE_OF_PART, get_structure, max_score
from app.models.enums import QuestionType

MCQ, TF, SHORT = QuestionType.multiple_choice, QuestionType.true_false, QuestionType.short_answer


def test_math_structure():
    s = get_structure("toan")
    assert s.duration_minutes == 90
    assert s.question_counts == {MCQ: 12, TF: 4, SHORT: 6}
    assert s.points[MCQ] == Decimal("0.25")
    assert s.points[SHORT] == Decimal("0.5")


@pytest.mark.parametrize("subject", ["ly", "hoa", "sinh"])
def test_science_structure(subject):
    s = get_structure(subject)
    assert s.duration_minutes == 50
    assert s.question_counts == {MCQ: 18, TF: 4, SHORT: 6}
    assert s.points[MCQ] == Decimal("0.25")
    assert s.points[SHORT] == Decimal("0.25")


def test_true_false_points_follow_number_of_correct_statements():
    # 0 ý: 0 · 1 ý: 0,1 · 2 ý: 0,25 · 3 ý: 0,5 · 4 ý: 1 – chung cho mọi môn.
    for subject in ("toan", "ly", "hoa", "sinh"):
        assert get_structure(subject).true_false_points == tuple(
            Decimal(p) for p in ("0", "0.1", "0.25", "0.5", "1")
        )


@pytest.mark.parametrize("subject", ["toan", "ly", "hoa", "sinh"])
def test_full_structure_is_worth_10_points(subject):
    s = get_structure(subject)
    assert max_score(s, s.question_counts) == Decimal(10)


def test_part_determines_question_type():
    assert TYPE_OF_PART == {"I": MCQ, "II": TF, "III": SHORT}


def test_unknown_subject_is_rejected():
    with pytest.raises(ValueError, match="van"):
        get_structure("van")
