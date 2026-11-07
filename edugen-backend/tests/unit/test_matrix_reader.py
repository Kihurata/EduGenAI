"""Đọc ma trận từ markdown do marker sinh (bảng HTML giữ rowspan/colspan).

Mẫu thật: tests/fixtures/matrices/ktgk_hk1_toan10.md, chạy marker trên ktgk_hk1_toan10.png.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.matrix_reader import check_totals, parse_matrix_markdown, read_matrix
from app.models.enums import Level, QuestionType

FIXTURE = Path(__file__).parents[1] / "fixtures" / "matrices" / "ktgk_hk1_toan10.md"
MC, TF, SA = QuestionType.multiple_choice, QuestionType.true_false, QuestionType.short_answer
B, H, VD = Level.biet, Level.hieu, Level.van_dung

HEAD = (
    '<tr><th rowspan="4">TT</th><th rowspan="4">Chủ đề/Chương</th>'
    '<th rowspan="4">Nội dung/đơn vị kiến thức</th><th colspan="9">Năng lực toán học</th></tr>'
    '<tr><th colspan="3">NL tư duy</th><th colspan="3">NL giải quyết vấn đề</th><th colspan="3">NL mô hình hóa</th></tr>'
    '<tr><th colspan="3">TN Nhiều lựa chọn</th><th colspan="3">"Đúng – Sai"</th><th colspan="3">Trả lời ngắn</th></tr>'
    "<tr>" + "<th>Biết</th><th>Hiểu</th><th>Vận dụng</th>" * 3 + "</tr>"
)
TITLE = "Môn: Toán học - Lớp: 10\n\nTên ma trận: Thử\n\n"


def td(text: str = "", rowspan: int = 1) -> str:
    span = f' rowspan="{rowspan}"' if rowspan > 1 else ""
    return f"<td{span}>{text}</td>"


def tr(*cells: str) -> str:
    return "<tr>" + "".join(cells) + "</tr>"


def matrix_md(*rows: str, title: str = TITLE) -> str:
    return f"{title}<table>{HEAD}{''.join(rows)}</table>\n"


def one_topic(*values: str) -> str:
    """Một chủ đề một đơn vị kiến thức; values là 9 ô MC B/H/VD, TF B/H/VD, SA B/H/VD."""
    cells = list(values) + [""] * (9 - len(values))
    return matrix_md(tr(td("1"), td("Chủ đề A"), td("Đơn vị 1"), *map(td, cells)))


def summary(cell) -> tuple:
    return (
        cell.type, cell.topic, cell.content_unit, cell.level, cell.count,
        cell.statement_levels, cell.competency_codes,
    )  # fmt: skip


def messages(issues) -> str:
    return " | ".join(i.message for i in issues)


# ----- Mẫu thật -----


@pytest.fixture(scope="module")
def real():
    return read_matrix(FIXTURE.read_text(encoding="utf-8"))


def test_real_matrix_header(real):
    assert (real.subject, real.grade, real.name) == ("toan", 10, "KTGK - HK1 - 10")


def test_real_matrix_has_no_issues(real):
    assert real.issues == []


def test_real_matrix_cells_in_exam_order(real):
    T1 = "Mệnh đề và tập hợp"
    T2 = "Bất phương trình và hệ bất phương trình bậc nhất hai ẩn"
    T3 = "Hệ thức lượng trong tam giác"
    U12 = "Tập hợp-Các phép toán trên tập hợp"
    U21, U22 = "Bất pt bậc nhất hai ẩn", "Hệ bất pt bậc nhất hai ẩn"
    U31, U32 = "Giá trị lượng giác của một góc", "Hệ thức lượng trong tam giác"
    BBHH = (B, B, H, H)
    TF_CODES = ("GQ1.4", "GQ2.1")
    assert [summary(c) for c in real.cells] == [
        (MC, T1, "Mệnh đề", B, 2, None, ("TD1.2",)),
        (MC, T1, U12, B, 2, None, ("TD1.2",)),
        (MC, T1, U12, H, 1, None, ("TD1.3",)),
        (MC, T2, U21, B, 1, None, ("TD1.2",)),
        (MC, T2, U21, H, 1, None, ("TD1.3",)),
        (MC, T2, U22, B, 1, None, ("TD1.2",)),
        (MC, T3, U31, B, 1, None, ("TD1.2",)),
        (MC, T3, U31, H, 1, None, ("TD1.3",)),
        (MC, T3, U32, B, 1, None, ("TD1.2",)),
        (MC, T3, U32, H, 1, None, ("TD1.3",)),
        # Đúng–Sai gộp dọc cả chủ đề → content_unit None; "2a, 2b" = 2 câu.
        (TF, T1, None, H, 2, BBHH, TF_CODES),
        (TF, T2, None, H, 1, BBHH, TF_CODES),
        (TF, T3, U32, H, 1, BBHH, TF_CODES),
        (SA, T1, U12, H, 1, None, ()),
        (SA, T1, U12, VD, 1, None, ()),
        (SA, T2, U21, H, 1, None, ()),
        (SA, T2, U22, VD, 1, None, ()),
        (SA, T3, None, VD, 2, None, ()),
    ]


def test_real_matrix_declared_totals(real):
    assert real.declared_counts[(TF, B)] == 8  # Đúng–Sai đếm theo ý
    assert real.declared_points[(SA, VD)] == Decimal("2.00")


# ----- Phần đầu -----


def test_missing_header_lines_are_issues():
    parsed = parse_matrix_markdown(matrix_md(title=""))
    assert "Môn" in messages(parsed.issues)
    assert "Tên ma trận" in messages(parsed.issues)


@pytest.mark.parametrize("name, code", [
    ("Vật lí", "ly"), ("Vật lý", "ly"), ("Lý", "ly"), ("Lí", "ly"),
    ("Hóa học", "hoa"), ("Hoá học", "hoa"), ("Hóa", "hoa"), ("Hoá", "hoa"),
])
def test_physics_and_chemistry_subject_lines_are_read(name, code):
    parsed = parse_matrix_markdown(matrix_md(title=f"Môn: {name} - Lớp: 12\n\nTên ma trận: X\n\n"))
    assert parsed.subject == code
    assert "Môn" not in messages(parsed.issues)


def test_unsupported_subject_is_issue():
    parsed = parse_matrix_markdown(matrix_md(title="Môn: Văn - Lớp: 10\n\nTên ma trận: X\n\n"))
    assert parsed.subject is None
    assert "Văn" in messages(parsed.issues)


def test_grade_outside_10_12_is_issue():
    parsed = parse_matrix_markdown(matrix_md(title="Môn: Toán học - Lớp: 9\n\nTên ma trận: X\n\n"))
    assert "Lớp 9" in messages(parsed.issues)


def test_pipe_table_without_html_is_issue():
    parsed = parse_matrix_markdown(TITLE + "| TT | Chủ đề |\n|---|---|\n| 1 | A |\n")
    assert parsed.cells == []
    assert "html_tables_in_markdown" in messages(parsed.issues)


# ----- Ô nhiều lựa chọn / trả lời ngắn -----


@pytest.mark.parametrize(
    ("text", "count", "codes"),
    [
        ("02 (TD1.2)", 2, ("TD1.2",)),
        ("1", 1, ()),
        ("3 (TD1.2, TD1.3)", 3, ("TD1.2", "TD1.3")),
        ("01<br/>(TD1.3)", 1, ("TD1.3",)),
    ],
)
def test_count_cell(text, count, codes):
    [cell] = parse_matrix_markdown(one_topic(text)).cells
    assert (cell.type, cell.level, cell.count, cell.competency_codes) == (MC, B, count, codes)


def test_zero_count_cell_is_treated_as_empty():
    assert parse_matrix_markdown(one_topic("0", "00")).cells == []


def test_unreadable_cell_is_issue_with_location():
    parsed = parse_matrix_markdown(one_topic("", "hai câu"))
    [issue] = parsed.issues
    assert "hai câu" in issue.message
    assert issue.location == "Chủ đề A › Đơn vị 1 › Nhiều lựa chọn / Hiểu"


# ----- Ô Đúng–Sai -----


def test_true_false_statements_spread_over_levels():
    md = one_topic("", "", "", "a", "b, c", "d")
    [cell] = parse_matrix_markdown(md).cells
    assert (cell.type, cell.count, cell.level, cell.statement_levels) == (TF, 1, VD, (B, H, H, VD))


def test_true_false_question_count_prefix():
    [cell] = parse_matrix_markdown(one_topic("", "", "", "3a, 3b, 3c", "3d")).cells
    assert cell.count == 3


def test_true_false_missing_statement_is_issue():
    parsed = parse_matrix_markdown(one_topic("", "", "", "a, b", "c"))
    assert parsed.cells == []
    assert "a–d" in messages(parsed.issues)


def test_true_false_duplicate_statement_is_issue():
    parsed = parse_matrix_markdown(one_topic("", "", "", "a, b", "b, c, d"))
    assert "a–d" in messages(parsed.issues)


def test_true_false_inconsistent_question_count_is_issue():
    parsed = parse_matrix_markdown(one_topic("", "", "", "2a, 2b", "c, d"))
    assert "số câu" in messages(parsed.issues)


def test_true_false_plain_number_is_issue():
    parsed = parse_matrix_markdown(one_topic("", "", "", "2"))
    assert "Đúng – Sai" in parsed.issues[0].location


# ----- Ô gộp dọc -----


def two_unit_topic(first_row_values: list[str], second_row_values: list[str]) -> str:
    return matrix_md(
        tr(td("1", 2), td("Chủ đề A", 2), td("Đơn vị 1"), *first_row_values),
        tr(td("Đơn vị 2"), *second_row_values),
    )


def test_cell_merged_over_whole_topic_belongs_to_topic():
    first = [td()] * 8 + [td("2", 2)]  # SA Vận dụng gộp 2 hàng
    parsed = parse_matrix_markdown(two_unit_topic(first, [td()] * 8))
    [cell] = parsed.cells
    assert (cell.topic, cell.content_unit, cell.count) == ("Chủ đề A", None, 2)


def test_unmerged_cell_in_second_row_keeps_its_unit():
    second = [td("1")] + [td()] * 8
    [cell] = parse_matrix_markdown(two_unit_topic([td()] * 9, second)).cells
    assert cell.content_unit == "Đơn vị 2"


def test_cell_merged_over_part_of_topic_lists_units():
    md = matrix_md(
        tr(td("1", 3), td("Chủ đề A", 3), td("Đơn vị 1"), td("1", 2), *[td()] * 8),
        tr(td("Đơn vị 2"), *[td()] * 8),
        tr(td("Đơn vị 3"), *[td()] * 9),
    )
    [cell] = parse_matrix_markdown(md).cells
    assert cell.content_unit == "Đơn vị 1; Đơn vị 2"


def test_cell_merged_across_topics_is_issue():
    md = matrix_md(
        tr(td("1"), td("Chủ đề A"), td("Đơn vị 1"), td("1", 2), *[td()] * 8),
        tr(td("2"), td("Chủ đề B"), td("Đơn vị 2"), *[td()] * 8),
    )
    assert "nhiều chủ đề" in messages(parse_matrix_markdown(md).issues)


# ----- Đối chiếu hàng tổng -----


def with_totals(counts: list[str], points: list[str]) -> str:
    body = tr(td("1"), td("Chủ đề A"), td("Đơn vị 1"), *map(td, ["4", "", "", "a, b", "c, d"]), *[td()] * 4)
    totals = tr(td(), td(), td("<b>Tổng số câu</b>"), *(td(f"<b>{c}</b>") for c in counts))
    pts = tr(td(), td(), td("<b>Tổng số điểm</b>"), *(td(f"<b>{p}</b>") for p in points))
    return matrix_md(body, totals, pts)


def test_totals_match():
    # 4 câu MC × 0.25 = 1; 1 câu Đúng–Sai: 2 ý Biết + 2 ý Hiểu, mỗi ý 0.25.
    md = with_totals(["4", "0", "0", "2", "2", "0", "0", "0", "0"], ["1.00", "0", "0", "0.50", "0,50", "0", "0", "0", "0"])
    parsed = parse_matrix_markdown(md)
    issues = check_totals(parsed)
    assert [i.message for i in issues if "Tổng điểm" not in i.message] == []


def test_declared_count_mismatch_is_issue():
    md = with_totals(["5", "0", "0", "2", "2", "0", "0", "0", "0"], [""] * 9)
    [issue] = [i for i in check_totals(parse_matrix_markdown(md)) if "Tổng số câu" in i.message]
    assert "5" in issue.message and "4" in issue.message
    assert issue.location == "Nhiều lựa chọn / Biết"


def test_declared_points_mismatch_is_issue():
    md = with_totals([""] * 9, ["2.00", "", "", "", "", "", "", "", ""])
    [issue] = [i for i in check_totals(parse_matrix_markdown(md)) if "Tổng số điểm" in i.message]
    assert issue.location == "Nhiều lựa chọn / Biết"


def test_total_score_must_be_10():
    md = with_totals([""] * 9, [""] * 9)
    assert "Tổng điểm của ma trận là 2, phải bằng 10" in messages(check_totals(parse_matrix_markdown(md)))


def test_read_matrix_collects_parse_and_total_issues():
    reading = read_matrix(one_topic("", "hai câu"))
    assert len(reading.issues) == 4  # ô không đọc được + thiếu 2 hàng tổng + tổng điểm 0


def test_missing_totals_rows_is_issue():
    # Không có hàng tổng thì không đối chiếu được lỗi đọc ảnh → không cho qua.
    md = matrix_md(tr(td("1"), td("Chủ đề A"), td("Đơn vị 1"), td("4"), *[td()] * 8))
    messages_ = [i.message for i in check_totals(parse_matrix_markdown(md))]
    assert any("hàng 'Tổng số câu'" in m for m in messages_)
    assert any("hàng 'Tổng số điểm'" in m for m in messages_)


def test_true_false_keeps_codes_and_text_per_statement(real):
    [first_tf] = [c for c in real.cells if c.type is TF][:1]
    assert first_tf.statement_codes == (("GQ1.4",), ("GQ1.4",), ("GQ2.1",), ("GQ2.1",))
    assert first_tf.statement_texts[0] == first_tf.statement_texts[1] != first_tf.statement_texts[2]
    assert "2a, 2b" in first_tf.statement_texts[0]
    assert "GQ1.4" in first_tf.statement_texts[0]


def test_group_issues_merges_identical_messages_and_locations():
    from app.domain.matrix_reader import MatrixIssue, group_issues

    issues = [
        MatrixIssue("Sửa A", "Ô 3"), MatrixIssue("Sửa B"), MatrixIssue("Sửa A", "Ô 5"),
        MatrixIssue("Sửa A", "Ô 3"), MatrixIssue("Sửa B"),
    ]  # fmt: skip
    assert group_issues(issues) == [MatrixIssue("Sửa A", "Ô 3, Ô 5"), MatrixIssue("Sửa B")]


def test_group_issues_keeps_unlocated_occurrence_separate():
    from app.domain.matrix_reader import MatrixIssue, group_issues

    issues = [MatrixIssue("Sửa A"), MatrixIssue("Sửa A", "Ô 3"), MatrixIssue("Sửa A", "Ô 5")]
    assert group_issues(issues) == [MatrixIssue("Sửa A"), MatrixIssue("Sửa A", "Ô 3, Ô 5")]


def test_grade_issue_says_how_to_fix():
    parsed = parse_matrix_markdown(matrix_md(title="Môn: Toán học - Lớp: 9\n\nTên ma trận: X\n\n"))
    assert "Lớp 9 không hợp lệ" in messages(parsed.issues) and "ghi lại" in messages(parsed.issues)
