"""Payload ô gửi RAG và dựng danh sách ô từ ma trận đã đọc.

Đầu ra mong muốn:
- Payload gửi chủ đề + đơn vị kiến thức dạng text tiếng Việt, kèm lớp và mã năng lực.
- Ô gộp trùm cả chủ đề gửi content_unit = null. statement_levels chỉ có ở Đúng–Sai.
- Ô đánh số từ 1 theo thứ tự ma trận (Phần I → II → III).
- Ma trận thiếu môn/lớp hoặc còn lỗi thì không dựng được ô.
"""

from pathlib import Path

import pytest

from app.domain.cell import PAYLOAD_KEYS, Cell, cells_from_matrix
from app.domain.matrix_reader import MatrixIssue, ParsedCell, ParsedMatrix, read_matrix
from app.models.enums import Level, QuestionType

FIXTURE = Path(__file__).parents[1] / "fixtures" / "matrices" / "ktgk_hk1_toan10.md"
MC, TF, SA = QuestionType.multiple_choice, QuestionType.true_false, QuestionType.short_answer
B, H, VD = Level.biet, Level.hieu, Level.van_dung

MC_CELL = Cell(1, "toan", 10, "Mệnh đề và tập hợp", "Mệnh đề", MC, B, 2, competency_codes=("TD1.2",))
TF_CELL = Cell(
    11, "toan", 10, "Mệnh đề và tập hợp", None, TF, H, 2, (B, B, H, H), ("GQ1.4", "GQ2.1")
)


def test_multiple_choice_payload():
    assert MC_CELL.to_payload() == {
        "subject": "toan",
        "grade": 10,
        "topic": "Mệnh đề và tập hợp",
        "content_unit": "Mệnh đề",
        "type": "multiple_choice",
        "level": "Biết",
        "count": 2,
        "competency_codes": ["TD1.2"],
    }


def test_true_false_payload_has_statement_levels_and_null_content_unit():
    payload = TF_CELL.to_payload()
    assert payload["content_unit"] is None
    assert payload["statement_levels"] == ["Biết", "Biết", "Hiểu", "Hiểu"]
    assert payload["competency_codes"] == ["GQ1.4", "GQ2.1"]


def test_payload_keys_match_documented_format():
    assert set(MC_CELL.to_payload()) == set(PAYLOAD_KEYS) - {"statement_levels", "statement_units"}
    assert set(TF_CELL.to_payload()) == set(PAYLOAD_KEYS) - {"statement_units"}  # chỉ có khi biết nội dung từng ý


def test_cell_without_competency_codes_sends_empty_list():
    cell = Cell(1, "toan", 10, "Hệ thức lượng trong tam giác", None, SA, VD, 2)
    assert cell.to_payload()["competency_codes"] == []
    assert cell.part == "III"


def test_cells_from_real_matrix_are_numbered_in_order():
    parsed = read_matrix(FIXTURE.read_text(encoding="utf-8"))
    cells = cells_from_matrix(parsed)
    assert [c.id for c in cells] == list(range(1, 19))
    assert {(c.subject, c.grade) for c in cells} == {("toan", 10)}
    assert [c.part for c in cells] == ["I"] * 10 + ["II"] * 3 + ["III"] * 5
    assert cells[0] == MC_CELL
    assert cells[10] == TF_CELL


def test_cells_copy_every_field_of_parsed_cell():
    parsed = ParsedMatrix(
        subject="toan",
        grade=11,
        cells=[ParsedCell(SA, "Hàm số", "Đạo hàm", VD, 1, competency_codes=("GQ1.4",))],
    )
    assert cells_from_matrix(parsed) == [Cell(1, "toan", 11, "Hàm số", "Đạo hàm", SA, VD, 1, None, ("GQ1.4",))]


@pytest.mark.parametrize(
    "parsed, message",
    [
        (ParsedMatrix(subject=None, grade=10), "môn"),
        (ParsedMatrix(subject="toan", grade=None), "lớp"),
        (ParsedMatrix(subject="toan", grade=10, issues=[MatrixIssue("lệch tổng")]), "còn lỗi"),
    ],
)
def test_incomplete_or_invalid_matrix_cannot_build_cells(parsed, message):
    with pytest.raises(ValueError, match=message):
        cells_from_matrix(parsed)


def test_true_false_payload_has_content_unit_of_each_statement():
    units = ("Mệnh đề", "Mệnh đề", "Tập hợp", "Tập hợp")
    cell = Cell(11, "toan", 10, "Mệnh đề và tập hợp", None, TF, H, 1, (B, B, H, H), statement_units=units)
    assert cell.to_payload()["statement_units"] == list(units)
    assert "statement_units" not in TF_CELL.to_payload()
    assert cell.unit_label == "Mệnh đề; Tập hợp"
    assert MC_CELL.unit_label == "Mệnh đề"
