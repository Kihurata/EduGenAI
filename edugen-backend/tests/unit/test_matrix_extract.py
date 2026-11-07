"""Tóm tắt: đọc ma trận từ JSON Gemini trích (D-016, T-054): ghép ý Đúng–Sai thành câu, kiểm 12/4/6, chủ đề chưa có mã.

Đầu ra mong muốn (TC-020 hai ma trận thật, TC-021 các quy tắc):
- Ma trận giữa kì Toán 12 (có mã câu C1a…) và đề tham khảo Bộ 2025 (không có mã, trộn lớp 11 và 12)
  đều ra đúng 12 MC + 4 câu Đúng–Sai + 6 trả lời ngắn, lớp ma trận là lớp lớn nhất.
- Ý Đúng–Sai có mã câu ghép theo mã; không có mã thì ghép tuần tự theo hàng, 4 ý một câu, mức tăng dần.
- Câu rải nhiều đơn vị: content_unit None; câu ghép nhiều chủ đề: chủ đề nhiều ý nhất.
- Lỗi (số ý lệch, tổng khác 12/4/6, chủ đề không có mã, JSON hỏng) thành MatrixIssue, không ném lỗi.
"""

import copy
import json
from collections import Counter
from pathlib import Path

from app.domain.matrix_reader import MatrixIssue, ParsedMatrix, read_matrix
from app.domain.topics import TOPICS
from app.models.enums import Level, QuestionType

FIXTURES = Path(__file__).parents[1] / "fixtures" / "matrix_extract"
MC, TF, SA = QuestionType.multiple_choice, QuestionType.true_false, QuestionType.short_answer
B, H, V = Level.biet, Level.hieu, Level.van_dung


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def read(data: dict) -> ParsedMatrix:
    return read_matrix(json.dumps(data, ensure_ascii=False))


def counts(parsed: ParsedMatrix) -> dict:
    """Số câu mỗi dạng; Đúng–Sai đếm theo câu."""
    total = Counter()
    for c in parsed.cells:
        total[c.type] += c.count
    return dict(total)


def messages(parsed: ParsedMatrix) -> list[str]:
    return [i.message for i in parsed.issues]


def row(unit, grade=12, code=None, mc=(0, 0, 0), tf=(0, 0, 0), sa=(0, 0, 0), items=()):
    def counts_of(t):
        return dict(zip(("biet", "hieu", "van_dung"), t, strict=True))

    return {"unit_name": unit, "grade": grade, "topic_code": code, "multiple_choice": counts_of(mc),
            "true_false_statements": counts_of(tf), "short_answer": counts_of(sa),
            "true_false_items": [{"cau": c, "y": y, "level": lv} for c, y, lv in items]}  # fmt: skip


def padded(*rows, pad_tf=True):
    """Ma trận Toán có các hàng cho trước; MC và trả lời ngắn (và Đúng–Sai nếu pad_tf) còn thiếu dồn vào hàng 'đệm' để đủ 12/4/6."""
    data = {"subject": "Toán", "name": "t", "rows": list(rows)}
    have = Counter()
    for r in rows:
        have["mc"] += sum(r["multiple_choice"].values())
        have["tf"] += sum(r["true_false_statements"].values())
        have["sa"] += sum(r["short_answer"].values())
    data["rows"].append(row("Đệm", code="dao_ham", mc=(12 - have["mc"], 0, 0), tf=(16 - have["tf"] if pad_tf else 0, 0, 0),
                            sa=(6 - have["sa"], 0, 0)))  # fmt: skip
    return data


# ----- TC-020: hai ma trận thật -----


def test_TC_020_mid_term_matrix_with_question_codes():
    parsed = read(load("giua_ki_toan12"))
    assert messages(parsed) == []
    assert (parsed.subject, parsed.grade) == ("toan", 12)
    assert counts(parsed) == {MC: 12, TF: 4, SA: 6}
    tf = [c for c in parsed.cells if c.type is TF]
    assert all(c.statement_levels == (B, B, H, H) for c in tf)  # C1–C4: a, b Biết; c, d Hiểu
    assert all(c.content_unit is None for c in tf)  # mỗi câu rải 2–3 đơn vị kiến thức
    assert {c.topic for c in parsed.cells} == {TOPICS["ung_dung_dao_ham"].name}


def test_TC_020_ministry_matrix_mixes_grades_and_has_no_question_codes():
    parsed = read(load("bo_2025_toan"))
    assert (parsed.subject, parsed.grade) == ("toan", 12)  # lớp lớn nhất
    assert counts(parsed) == {MC: 12, TF: 4, SA: 6}
    levels = [c.statement_levels for c in parsed.cells if c.type is TF]
    assert levels == [(B, B, H, H), (B, H, V, V), (B, H, H, H), (H, H, H, V)]  # ghép tuần tự theo hàng
    mixed = next(c for c in parsed.cells if c.type is TF and c.statement_levels == (B, H, V, V))
    assert mixed.topic == TOPICS["xac_suat_co_dieu_kien"].name  # 3 ý có điều kiện, 1 ý cổ điển
    assert "Xác suất cổ điển" in mixed.source_text  # ghi chú chủ đề của ý còn lại
    # 3 hàng không có mã chủ đề: báo ở màn hình kiểm tra, không đoán mã
    assert sorted(i.location for i in parsed.issues) == ["Hình học không gian", "Lý thuyết đồ thị", "Xác suất cổ điển"]
    assert all("chưa có mã chủ đề" in i.message for i in parsed.issues)


# ----- TC-021: quy tắc -----


def test_TC_021_items_with_codes_are_grouped_by_question_across_rows():
    data = padded(
        row("Đơn vị 1", code="dao_ham", tf=(2, 0, 0), items=[("C1", "a", "biet"), ("C1", "b", "biet")]),
        row("Đơn vị 2", code="dao_ham", tf=(0, 2, 0), items=[("C1", "c", "hieu"), ("C1", "d", "hieu")]),
        pad_tf=False,
    )
    parsed = read(data)
    first = next(c for c in parsed.cells if c.type is TF and c.statement_levels == (B, B, H, H))
    assert first.content_unit is None and first.count == 1


def test_TC_021_question_missing_a_statement_is_reported():
    data = padded(row("Đơn vị 1", code="dao_ham", tf=(2, 1, 0), items=[("C1", "a", "biet"), ("C1", "b", "biet"), ("C1", "c", "hieu")]), pad_tf=False)
    assert any("cần đủ 4 ý a–d" in m for m in messages(read(data)))


def test_TC_021_items_that_disagree_with_counts_are_reported_and_counts_win():
    data = load("giua_ki_toan12")
    data["rows"][0]["true_false_items"].pop()  # Gemini sót một ý
    parsed = read(data)
    assert any("Danh sách ý" in m for m in messages(parsed))
    assert counts(parsed) == {MC: 12, TF: 4, SA: 6}  # vẫn ghép được từ số lượng


def test_TC_021_true_false_statements_must_fill_whole_questions():
    data = padded(row("Đơn vị 1", code="dao_ham", tf=(3, 0, 0)), pad_tf=False)  # 3 ý
    assert any("không chia hết cho 4" in m for m in messages(read(data)))


def test_TC_021_totals_other_than_12_4_6_are_rejected():
    data = load("giua_ki_toan12")
    data["rows"][0]["multiple_choice"]["biet"] += 1  # 13 câu Phần I
    assert any("Phần I cần đủ 12 câu nhiều lựa chọn, hiện có 13: bớt 1 câu" in m for m in messages(read(data)))


def test_TC_021_unknown_topic_code_is_treated_as_missing():
    data = padded(row("Chuyên đề lạ", code="khong_co_that", mc=(1, 0, 0)))
    issues = [i for i in read(data).issues if i.location == "Chuyên đề lạ"]
    assert len(issues) == 1 and "chưa có mã chủ đề" in issues[0].message


def test_TC_021_ambiguous_row_without_code_but_known_name_resolves():
    data = padded(row("Đạo hàm", grade=11, code=None, mc=(1, 0, 0)))
    assert [i for i in read(data).issues if i.location == "Đạo hàm"] == []


def test_TC_021_bad_json_and_unknown_subject_become_issues():
    assert messages(read_matrix("{không phải json")) == ["Không đọc được kết quả Gemini: không phải JSON"]
    data = copy.deepcopy(load("giua_ki_toan12"))
    data["subject"] = "Âm nhạc"
    assert "Môn 'Âm nhạc' chưa được hỗ trợ" in messages(read(data))


def test_TC_021_missing_grades_are_reported():
    data = load("giua_ki_toan12")
    for r in data["rows"]:
        r["grade"] = r["topic_code"] = None  # không ghi lớp và không nhận ra chương nào
    parsed = read(data)
    assert parsed.grade is None and any(m.startswith("Không xác định được lớp của ma trận: ghi lớp") for m in messages(parsed))


def test_TC_021_issue_type_is_the_existing_one():
    assert all(isinstance(i, MatrixIssue) for i in read(load("bo_2025_toan")).issues)


# ----- TC-022: kết quả Gemini lệch khuôn vẫn đọc đúng -----


def test_TC_022_summary_rows_are_not_content():
    """Gemini hay chép cả hàng tổng/tỉ lệ của bảng thành rows: không được cộng chúng vào ma trận."""
    data = copy.deepcopy(load("giua_ki_toan12"))
    data["rows"] += [
        row("Tổng số câu", grade=None, mc=(8, 4, 0), tf=(8, 8, 0), sa=(0, 0, 6)),
        row("Tổng số điểm", grade=None, mc=(2, 1, 0), tf=(2, 2, 0), sa=(0, 0, 3)),
        row("Tỉ lệ %", grade=None, mc=(20, 10, 0), tf=(20, 20, 0), sa=(0, 0, 30)),
        row("TỔNG", grade=None, mc=(8, 4, 0)),
    ]
    parsed = read(data)
    assert counts(parsed) == {MC: 12, TF: 4, SA: 6}
    assert parsed.issues == []


def test_TC_022_unit_name_starting_with_tong_is_still_content():
    data = padded(row("Tổng và hiệu của hai vectơ", grade=10, mc=(1, 0, 0)))
    assert any(c.content_unit == "Tổng và hiệu của hai vectơ" for c in read(data).cells)


def test_TC_022_rows_without_any_count_raise_no_topic_issue():
    """Hàng tiêu đề chương (không có số nào) không sinh ô nên không báo thiếu mã chủ đề."""
    data = copy.deepcopy(load("giua_ki_toan12"))
    data["rows"].insert(0, row("Chương I. Một chương lạ"))
    assert read(data).issues == []


def test_TC_022_statement_letter_written_with_question_number():
    """y = '1a' / 'C1a' / 'A' vẫn là ý a."""
    for spell in (lambda c, y: c.lstrip("C") + y, lambda c, y: "C" + c.lstrip("C") + y, lambda c, y: y.upper()):
        data = copy.deepcopy(load("giua_ki_toan12"))
        for r in data["rows"]:
            for item in r["true_false_items"]:
                item["y"] = spell(item["cau"], item["y"])
        parsed = read(data)
        assert counts(parsed) == {MC: 12, TF: 4, SA: 6} and parsed.issues == [], messages(parsed)


def test_TC_022_unreadable_items_fall_back_instead_of_crashing():
    data = copy.deepcopy(load("giua_ki_toan12"))
    data["rows"][0]["true_false_items"][0]["cau"] = "Câu"  # không có số
    parsed = read(data)
    assert counts(parsed)[TF] == 4
    data = copy.deepcopy(load("giua_ki_toan12"))
    data["rows"][0]["true_false_items"][0]["level"] = "nhan_biet"
    assert counts(read(data))[TF] == 4


def test_TC_022_subject_and_grade_spelled_loosely():
    data = copy.deepcopy(load("giua_ki_toan12"))
    data["subject"] = "Môn TOÁN 12"
    for r in data["rows"]:
        r["grade"] = str(r["grade"])
    parsed = read(data)
    assert (parsed.subject, parsed.grade) == ("toan", 12) and parsed.issues == []


# ----- TC-023: nội dung kiến thức của từng ý Đúng–Sai -----

U1 = "Tính đơn điệu và cực trị của hàm số"
U2 = "Giá trị lớn nhất và giá trị nhỏ nhất của hàm số"
U3 = "Đường tiệm cận của đồ thị hàm số"
U4 = "Khảo sát sự biến thiên và vẽ đồ thị của hàm số"


def test_TC_023_each_statement_keeps_its_content_unit():
    """Ma trận giữa kì: mỗi câu Đ/S rải 2–3 nội dung; ý nào thuộc nội dung nào phải giữ lại."""
    tf = [c for c in read(load("giua_ki_toan12")).cells if c.type is TF]
    assert [c.statement_units for c in tf] == [
        (U1, U2, U1, U1),  # C1a, C1b, C1c, C1d
        (U1, U2, U2, U1),  # C2b và "2c" ở hàng GTLN–GTNN
        (U3, U1, U1, U4),
        (U3, U3, U1, U4),
    ]


def test_TC_023_statement_units_follow_levels_when_grouped_sequentially():
    tf = [c for c in read(load("bo_2025_toan")).cells if c.type is TF]
    assert tf[0].statement_units == ("Lượng giác",) * 4
    assert tf[0].content_unit == "Lượng giác"  # cả 4 ý cùng một hàng
    assert tf[1].statement_units == ("Xác suất cổ điển",) + ("Xác suất có điều kiện",) * 3
    assert tf[1].content_unit is None


def test_TC_023_only_true_false_cells_have_statement_units():
    parsed = read(load("giua_ki_toan12"))
    assert all(c.statement_units is None for c in parsed.cells if c.type is not TF)


# ----- TC-024: đối chiếu cột Tổng của từng hàng, tên nội dung sạch -----


def test_TC_024_row_total_mismatch_points_at_the_row():
    """Cột Tổng (lệnh hỏi theo mức, Đ/S đếm theo ý) lệch với các phần đọc được → báo đúng hàng đó."""
    data = copy.deepcopy(load("giua_ki_toan12"))
    data["rows"][0]["row_totals"] = {"biet": 6, "hieu": 6, "van_dung": 0}  # đúng: MC 3+1, Đ/S 3+5 ý
    data["rows"][3]["row_totals"] = {"biet": 1, "hieu": 3, "van_dung": 3}
    data["rows"][3]["short_answer"] = {"biet": 0, "hieu": 3, "van_dung": 3}  # Gemini chép nhầm cột Tổng
    parsed = read(data)
    row_issues = [i for i in parsed.issues if "cột Tổng" in i.message]
    assert [i.location for i in row_issues] == [data["rows"][3]["unit_name"]]
    assert "Hiểu 3" in row_issues[0].message and "Hiểu 6" in row_issues[0].message


def test_TC_024_missing_or_empty_row_totals_are_not_checked():
    data = copy.deepcopy(load("giua_ki_toan12"))
    data["rows"][0]["row_totals"] = None
    data["rows"][1]["row_totals"] = {"biet": 0, "hieu": 0, "van_dung": 0}
    assert read(data).issues == []


def test_TC_024_lesson_hours_are_dropped_from_unit_names():
    data = copy.deepcopy(load("giua_ki_toan12"))
    data["rows"][0]["unit_name"] += " (6 tiết)"
    parsed = read(data)
    assert parsed.issues == []
    assert all("tiết" not in (u or "") for c in parsed.cells for u in (c.content_unit, *(c.statement_units or ())))


def test_TC_024_grade_comes_from_the_chapters_when_the_file_has_none():
    """Ảnh không ghi lớp: lớp ma trận là lớp lớn nhất của các chương đã có mã (SGK KNTT)."""
    data = copy.deepcopy(load("giua_ki_toan12"))
    for r in data["rows"]:
        r["grade"] = None
    parsed = read(data)
    assert parsed.grade == 12 and parsed.issues == []


def test_structure_message_says_how_many_cells_to_add():
    data = load("giua_ki_toan12")
    data["rows"][0]["multiple_choice"]["biet"] -= 2  # 10 câu Phần I
    assert any("hiện có 10: thêm 2 câu" in m for m in messages(read(data)))


def test_unknown_topic_issues_share_one_message_and_group_by_location():
    from app.domain.matrix_reader import group_issues

    parsed = read(load("bo_2025_toan"))
    grouped = group_issues(parsed.issues)
    topic_issues = [i for i in grouped if "mã chủ đề" in i.message]
    assert len(topic_issues) == 1
    assert topic_issues[0].location == "Hình học không gian, Lý thuyết đồ thị, Xác suất cổ điển"
    assert "sửa tên nội dung" in topic_issues[0].message  # nói rõ cách sửa
