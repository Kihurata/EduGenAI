"""Một ô ma trận gửi RAG: hợp đồng payload BE → RAG.

Format payload POST /generate (cần team RAG xác nhận), một request cho mỗi ô:

    {
      "subject": "toan",                      # mã môn; hiện chỉ có Toán
      "grade": 10,                            # lớp 10–12
      "topic": "Mệnh đề và tập hợp",          # chủ đề, text tiếng Việt như trên ma trận
      "content_unit": "Mệnh đề" | null,       # đơn vị kiến thức; null = cả chủ đề (ô gộp)
      "type": "multiple_choice" | "true_false" | "short_answer",
      "level": "Biết" | "Hiểu" | "Vận dụng",  # Đúng–Sai: mức cao nhất của 4 ý
      "count": 2,                             # số CÂU cần sinh
      "competency_codes": ["TD1.2"],          # mã năng lực, có thể rỗng
      "statement_levels": ["Biết", "Biết", "Hiểu", "Hiểu"],  # CHỈ true_false, mức ý a → d
      "statement_units": ["Mệnh đề", "Mệnh đề", "Tập hợp", null]  # CHỈ true_false khi biết, nội dung ý a → d
    }
"""

from dataclasses import dataclass
from typing import Any

from app.domain.exam_structure import PART_OF_TYPE
from app.domain.matrix_reader import ParsedMatrix
from app.models.enums import Level, QuestionType

PAYLOAD_KEYS = (
    "subject",
    "grade",
    "topic",
    "content_unit",
    "type",
    "level",
    "count",
    "competency_codes",
    "statement_levels",
    "statement_units",
)


@dataclass(frozen=True)
class Cell:
    """Một ô gửi RAG. `id` là số thứ tự ô trong ma trận (từ 1), không gửi đi."""

    id: int
    subject: str
    grade: int
    topic: str
    content_unit: str | None  # None khi ô gộp trùm cả chủ đề
    type: QuestionType
    level: Level
    count: int  # số CÂU
    statement_levels: tuple[Level, ...] | None = None  # chỉ true_false, ý a → d
    competency_codes: tuple[str, ...] = ()
    school_id: str | None = None  # RBAC: retrieval sees shared chunks plus this school's own
    teacher_id: str | None = None  # the teacher generating: also sees own sample exams, not colleagues'
    exam_kind: str | None = None  # D-017: tot_nghiep | dinh_ky_7991, retrieval prefers example items of this kind
    previous_stems: tuple[str, ...] = ()  # BUG-005: stems already in the exam, so RAG does not repeat them
    statement_units: tuple[str | None, ...] | None = None  # chỉ true_false: nội dung kiến thức ý a → d

    @property
    def unit_label(self) -> str:
        """Đơn vị kiến thức để hiển thị: content_unit, hoặc các nội dung của ý Đúng–Sai (bỏ trùng)."""
        if self.content_unit:
            return self.content_unit
        return "; ".join(dict.fromkeys(u for u in self.statement_units or () if u))

    @property
    def part(self) -> str:
        return PART_OF_TYPE[self.type]

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "subject": self.subject,
            "grade": self.grade,
            "topic": self.topic,
            "content_unit": self.content_unit,
            "type": self.type.value,
            "level": self.level.value,
            "count": self.count,
            "competency_codes": list(self.competency_codes),
        }
        if self.statement_levels is not None:
            payload["statement_levels"] = [lv.value for lv in self.statement_levels]
        if self.statement_units is not None:
            payload["statement_units"] = list(self.statement_units)
        return payload


def cells_from_matrix(parsed: ParsedMatrix) -> list[Cell]:
    """Dựng các ô gửi RAG từ ma trận đã đọc, giữ thứ tự Phần I → II → III."""
    if parsed.subject is None:
        raise ValueError("Ma trận chưa có môn học")
    if parsed.grade is None:
        raise ValueError("Ma trận chưa có lớp")
    if parsed.issues:
        raise ValueError("Ma trận còn lỗi, cần sửa trước khi sinh đề")
    return [
        Cell(
            id=i,
            subject=parsed.subject,
            grade=parsed.grade,
            topic=c.topic,
            content_unit=c.content_unit,
            type=c.type,
            level=c.level,
            count=c.count,
            statement_levels=c.statement_levels,
            competency_codes=c.competency_codes,
            statement_units=c.statement_units,
        )
        for i, c in enumerate(parsed.cells, start=1)
    ]
