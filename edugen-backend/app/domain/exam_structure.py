"""Cấu trúc đề tốt nghiệp THPT theo QĐ 764/2024.

Đây là nguồn duy nhất về số câu từng phần và thang điểm theo dạng câu; kiểm tra ma trận,
chấm điểm và phân tích câu hỏi đều đọc từ đây.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from app.models.enums import QuestionType

MCQ, TF, SHORT = QuestionType.multiple_choice, QuestionType.true_false, QuestionType.short_answer

# Phần trong đề → dạng câu, theo đúng thứ tự xuất hiện trong đề.
TYPE_OF_PART: dict[str, QuestionType] = {"I": MCQ, "II": TF, "III": SHORT}
PART_OF_TYPE: dict[QuestionType, str] = {t: p for p, t in TYPE_OF_PART.items()}
STATEMENTS_PER_TRUE_FALSE = 4

# Điểm câu đúng/sai theo số ý đúng 0..4, chung cho mọi môn.
TRUE_FALSE_POINTS = tuple(Decimal(p) for p in ("0", "0.1", "0.25", "0.5", "1"))
FULL_SCORE = Decimal(10)


@dataclass(frozen=True)
class ExamStructure:
    duration_minutes: int
    question_counts: dict[QuestionType, int]
    points: dict[QuestionType, Decimal]  # điểm tối đa một câu
    true_false_points: tuple[Decimal, ...] = TRUE_FALSE_POINTS


def _structure(duration: int, mcq_count: int, short_points: str) -> ExamStructure:
    return ExamStructure(
        duration_minutes=duration,
        question_counts={MCQ: mcq_count, TF: 4, SHORT: 6},
        points={MCQ: Decimal("0.25"), TF: TRUE_FALSE_POINTS[-1], SHORT: Decimal(short_points)},
    )


_SCIENCE = _structure(50, 18, "0.25")
STRUCTURES: dict[str, ExamStructure] = {
    "toan": _structure(90, 12, "0.5"),
    "ly": _SCIENCE,
    "hoa": _SCIENCE,
    "sinh": _SCIENCE,
}


def get_structure(subject: str) -> ExamStructure:
    try:
        return STRUCTURES[subject]
    except KeyError:
        raise ValueError(f"Môn chưa hỗ trợ: {subject}") from None


def max_score(structure: ExamStructure, counts: Mapping[QuestionType, int]) -> Decimal:
    """Tổng điểm tối đa với số câu mỗi dạng cho trước."""
    return sum((structure.points[t] * n for t, n in counts.items()), Decimal(0))
