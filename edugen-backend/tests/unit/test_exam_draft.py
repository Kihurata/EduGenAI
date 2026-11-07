"""Tóm tắt: kiểm tra bản nháp đề GV tải lên (T-050) trước khi nạp RAG. Bản nháp theo schema của
app.rag.chunking.exam; mỗi lỗi chỉ rõ câu nào (vd "II-2") để GV sửa trên màn hình duyệt.

Quy tắc: phần I/II/III; trắc nghiệm đủ A–D và đáp án là A–D; đúng/sai đủ 4 ý a–d có Đúng/Sai;
trả lời ngắn là một con số (dấu phẩy thập phân); chủ đề thuộc danh sách của môn; mức độ là
Biết/Hiểu/Vận dụng; lớp 10–12; loại đề trong danh sách; không trùng số câu trong một phần.
"""

import copy

import pytest

from app.domain.exam_draft import EXAM_KINDS, validate_exam_draft

MC = {"part": "I", "cau": 1, "topic": "ly/vat_li_nhiet", "stem": "Nhiệt độ sôi của nước ở 1 atm là",
      "options": {"A": "0 °C", "B": "100 °C", "C": "273 K", "D": "50 °C"}, "answer": "B", "level": "Biết"}
TF = {"part": "II", "cau": 1, "topic": "ly/khi_li_tuong", "stem": "Một lượng khí lí tưởng.",
      "statements": [{"label": l, "text": f"Ý {l}", "answer": l in "ac"} for l in "abcd"],
      "statement_levels": ["Biết", "Biết", "Hiểu", "Hiểu"]}
SA = {"part": "III", "cau": 1, "topic": "ly/vat_li_hat_nhan", "stem": "Chu kì bán rã (ngày)?", "answer": "-1,5"}
DRAFT = {"exam": "Đề thi thử Vật lí 2026", "ma_de": "101", "subject": "ly", "grade": 12, "official": False,
         "exam_kind": "tot_nghiep", "questions": [MC, TF, SA]}


def draft(**changes):
    d = copy.deepcopy(DRAFT)
    d.update(changes)
    return d


def with_question(i, **changes):
    d = draft()
    d["questions"][i].update(changes)
    return d


def messages(d, subject="ly"):
    return [(i.question, i.message) for i in validate_exam_draft(d, subject)]


def test_valid_draft_has_no_issues():
    assert messages(draft()) == []


def test_level_and_exam_kind_may_be_left_empty():
    d = with_question(0, level=None)
    d.pop("exam_kind")
    assert messages(d) == []


@pytest.mark.parametrize("changes, where, text", [
    ({"part": "IV"}, "IV-1", "Phần"),
    ({"stem": "  "}, "I-1", "đề bài"),
    ({"options": {"A": "x", "B": "y", "C": "z"}}, "I-1", "A–D"),
    ({"answer": "E"}, "I-1", "đáp án"),
    ({"topic": "dai_so_giai_tich/dao_ham"}, "I-1", "chủ đề"),
    ({"topic": ""}, "I-1", "chủ đề"),
    ({"level": "Khó"}, "I-1", "mức độ"),
])
def test_multiple_choice_rules(changes, where, text):
    [(question, message)] = messages(with_question(0, **changes))
    assert question == where and text in message


def test_true_false_needs_four_statements_with_answers():
    d = with_question(1, statements=TF["statements"][:3])
    assert any(q == "II-1" and "4 ý" in m for q, m in messages(d))
    d = with_question(1, statements=[dict(s, answer=None) for s in TF["statements"]])
    assert any(q == "II-1" and "Đúng/Sai" in m for q, m in messages(d))
    d = with_question(1, statement_levels=["Biết", "Biết", "Hiểu"])
    assert any(q == "II-1" and "mức độ" in m for q, m in messages(d))


@pytest.mark.parametrize("answer", ["", "1.5", "abc", "1,5 s"])
def test_short_answer_must_be_a_number_with_decimal_comma(answer):
    [(question, message)] = messages(with_question(2, answer=answer))
    assert question == "III-1" and "con số" in message


def test_exam_level_rules():
    assert any("Lớp" in m for _, m in messages(draft(grade=9)))
    assert any("loại đề" in m for _, m in messages(draft(exam_kind="bi_mat")))
    assert any("câu" in m for _, m in messages(draft(questions=[])))
    assert any("tên đề" in m for _, m in messages(draft(exam="")))


def test_duplicate_question_number_in_a_part_is_an_issue():
    d = draft(questions=[MC, dict(MC)])
    assert any(q == "I-1" and "trùng" in m for q, m in messages(d))


def test_topic_must_belong_to_the_exam_subject():
    assert any("chủ đề" in m for _, m in messages(draft(), subject="hoa"))


# --- T-055, TC-028: loại đề theo D-017 ---------------------------------------------------------------------------

def test_TC_028_exam_kinds_offered_to_teachers_are_the_d017_ones():
    from app.rag.manifest import EXAM_KINDS as INDEX_EXAM_KINDS

    assert EXAM_KINDS == ("tot_nghiep", "dinh_ky_7991") == INDEX_EXAM_KINDS


@pytest.mark.parametrize("old", ["thi_thu", "dinh_ky", "khac"])
def test_TC_028_old_exam_kinds_are_no_longer_accepted(old):
    assert any("loại đề" in m for _, m in messages(draft(exam_kind=old)))


@pytest.mark.parametrize("old, grade, new", [
    ("thi_thu", 12, "tot_nghiep"), ("thi_thu", 10, "tot_nghiep"),
    ("dinh_ky", 11, "dinh_ky_7991"), ("dinh_ky", 12, "dinh_ky_7991"),
    ("khac", 12, "tot_nghiep"), ("khac", 11, "dinh_ky_7991"), ("khac", 10, "dinh_ky_7991"),
    ("tot_nghiep", 10, "tot_nghiep"), ("dinh_ky_7991", 12, "dinh_ky_7991"),
    (None, 12, None), ("", 12, None),
])  # fmt: skip
def test_TC_028_old_exam_kinds_map_to_d017(old, grade, new):
    """D-017 mục 5: thi_thu → tot_nghiep, dinh_ky → dinh_ky_7991, khac theo lớp (12 → tot_nghiep, 10–11 → dinh_ky_7991)."""
    from app.domain.exam_draft import (
        migrate_exam_kind,  # hàm mới của T-055; import ở đây để test cũ trong file vẫn chạy
    )

    assert migrate_exam_kind(old, grade) == new


# --- T-055, TC-026: đáp án bị xoá thì GV phải điền trước khi xác nhận ---------------------------------------------

def test_TC_026_questions_without_answers_cannot_be_confirmed():
    d = draft()
    d["questions"][0]["answer"] = None
    d["questions"][1]["statements"][0]["answer"] = None
    d["questions"][2]["answer"] = None
    where = {q for q, _ in messages(d)}
    assert {"I-1", "II-1", "III-1"} <= where
