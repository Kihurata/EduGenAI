"""Ma trận đã đọc → JSON chuẩn của team và các ô gửi RAG.

JSON ma trận theo schema vault 06-testing/fixtures/toan-matrix/Toán matrices.md: `count`
đếm theo lệnh hỏi (Phần II: mỗi ý a–d một lệnh, 4 ý của một câu chung `question`), mức độ ghi
mã biet/hieu/vandung. Ô gửi RAG theo contract D-008: {subject, topic, level, type, count,
statement_levels?}, Phần II đếm theo CÂU. Chủ đề không có mã → issue, ô đó topic null.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.domain.exam_structure import (
    PART_OF_TYPE,
    STATEMENTS_PER_TRUE_FALSE,
    get_structure,
)
from app.domain.matrix_reader import MatrixIssue, ParsedCell, ParsedMatrix
from app.domain.topics import Topic, find_topic, topic_list_name
from app.models.enums import LEVEL_ORDER, Level, QuestionType

LEVEL_CODES = {Level.biet: "biet", Level.hieu: "hieu", Level.van_dung: "vandung"}
PARTS = ("I", "II", "III")

_PERIODIC_RE = re.compile(r"\b(KT)?(GK|CK)\d?\b|giữa kỳ|cuối kỳ", re.IGNORECASE)


@dataclass
class MatrixJson:
    matrix: dict[str, Any]
    rag_cells: list[dict[str, Any]]
    issues: list[MatrixIssue] = field(default_factory=list)

    @property
    def ready_for_rag(self) -> bool:
        return not self.issues


def exam_kind_of(name: str | None) -> str:
    """Đề định kỳ (CV 7991) khi tên có GK/CK/giữa kỳ/cuối kỳ, còn lại coi là đề tốt nghiệp."""
    return "dinh_ky_7991" if name and _PERIODIC_RE.search(name) else "tot_nghiep"


def _unique(values) -> list:
    return list(dict.fromkeys(values))


def _item_cells(cell: ParsedCell, base: dict[str, Any], first_question: int) -> list[dict[str, Any]]:
    """Một ô Đ/S `count` câu → mỗi câu một nhóm ô theo mức, count = số ý ở mức đó.

    Mã năng lực và chữ gốc lấy đúng từ các ý ở mức đó, không gộp cả câu.
    """
    statements = list(zip(cell.statement_levels, cell.statement_codes or [()] * 4,
                          cell.statement_texts or [None] * 4, strict=True))  # fmt: skip
    groups = []
    for lv in LEVEL_ORDER:
        at_level = [s for s in statements if s[0] is lv]
        if at_level:
            codes = _unique(code for _, codes, _ in at_level for code in codes)
            texts = _unique(text for _, _, text in at_level if text)
            groups.append((lv, len(at_level), codes, "; ".join(texts) or None))
    return [
        base | {
            "question": first_question + q, "level": LEVEL_CODES[lv], "count": n,
            "competency_codes": codes, "source_text": text,
        }
        for q in range(cell.count)
        for lv, n, codes, text in groups
    ]  # fmt: skip


def _cell_items(cell: ParsedCell, topic: Topic | None, first_question: int) -> list[dict[str, Any]]:
    """Ô ma trận → các ô JSON chuẩn: Đ/S tách theo câu và mức, loại khác giữ một ô."""
    base = {
        "strand": topic.strand if topic else None,
        "topic": topic.code if topic else None,
        "source_topic": cell.topic,
        "content_unit": cell.content_unit,
        "part": PART_OF_TYPE[cell.type],
        "type": cell.type.value,
    }
    if cell.statement_levels:
        return _item_cells(cell, base, first_question)
    return [base | {
        "level": LEVEL_CODES[cell.level], "count": cell.count,
        "competency_codes": list(cell.competency_codes), "source_text": cell.source_text,
    }]  # fmt: skip


def _rag_cell(cell: ParsedCell, subject: str, topic: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "subject": subject,
        "topic": topic,
        "level": cell.level.value,
        "type": cell.type.value,
        "count": cell.count,
    }
    if cell.statement_levels:
        payload["statement_levels"] = [lv.value for lv in cell.statement_levels]
    return payload


def build_matrix_json(parsed: ParsedMatrix) -> MatrixJson:
    if parsed.subject is None:
        raise ValueError("Ma trận chưa có môn, không dựng được JSON")
    subject = parsed.subject
    structure = get_structure(subject)
    need = {
        PART_OF_TYPE[t]: n * (STATEMENTS_PER_TRUE_FALSE if t is QuestionType.true_false else 1)
        for t, n in structure.question_counts.items()
    }
    issues: list[MatrixIssue] = []
    unknown: list[str] = []
    cells: list[dict[str, Any]] = []
    rag_cells: list[dict[str, Any]] = []
    level_totals = {p: dict.fromkeys(LEVEL_CODES.values(), 0) for p in PARTS}
    next_question = 1

    for cell in parsed.cells:
        topic = find_topic(cell.topic, grade=parsed.grade, subject=subject)
        if topic is None and cell.topic not in unknown:
            unknown.append(cell.topic)
        part = PART_OF_TYPE[cell.type]
        items = _cell_items(cell, topic, next_question)
        if cell.statement_levels:
            next_question += cell.count
        for item in items:
            level_totals[part][item["level"]] += item["count"]
        cells += items
        rag_cells.append(_rag_cell(cell, subject, topic.code if topic else None))

    issues += [
        MatrixIssue(f"Chủ đề '{name}' chưa có mã trong {topic_list_name(subject)}", name) for name in unknown
    ]
    total_items = {p: sum(level_totals[p].values()) for p in PARTS}
    # Điểm một lệnh hỏi: Đ/S tính 1/4 điểm tối đa của câu, như hàng "Tổng số điểm" trên ma trận.
    item_points = {
        PART_OF_TYPE[t]: p / (STATEMENTS_PER_TRUE_FALSE if t is QuestionType.true_false else 1)
        for t, p in structure.points.items()
    }
    score_totals = {
        p: {lv: float(item_points[p] * n) for lv, n in level_totals[p].items()} for p in PARTS
    }
    issues += [
        MatrixIssue(f"Phần {p} cần đủ {need[p]} lệnh hỏi, hiện có {total_items[p]}: sửa số lệnh hỏi ở các ô của phần này")
        for p in PARTS
        if total_items[p] != need[p]
    ]

    matrix = {
        "subject": subject,
        "grade": parsed.grade,
        "name": parsed.name,
        "exam_kind": exam_kind_of(parsed.name),
        "count_unit": "item",
        "cells": cells,
        "constraints": {
            "total_items": total_items,
            "level_totals": level_totals,
            "score_totals": score_totals,
            "total_score": sum(sum(s.values()) for s in score_totals.values()),
        },
    }
    return MatrixJson(matrix, rag_cells, issues + list(parsed.issues))
