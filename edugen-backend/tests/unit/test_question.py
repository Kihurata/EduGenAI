"""Câu hỏi RAG trả về (JSON `cau_hoi`) → câu hỏi của BE.

Đầu ra mong muốn:
- Đổi dạng câu/mức độ ASCII của RAG sang QuestionType/Level của BE và ngược lại.
- Câu đúng cấu trúc theo dạng được chuẩn hóa sang khóa của BE.
- Câu sai cấu trúc, sai dạng hoặc sai mức so với ô thì bị loại kèm lý do tiếng Việt.
- Câu của BE (GV sửa) đổi ngược được sang dạng RAG để kiểm lại bằng cùng bộ kiểm.
"""

import copy
import json
from pathlib import Path

import pytest

from app.domain.cell import Cell
from app.domain.question import (
    LEVEL_FROM_RAG,
    LEVEL_TO_RAG,
    parse_question,
    split_questions,
    stem_blocks,
    to_rag,
)
from app.models.enums import Level, QuestionType

SAMPLES = Path(__file__).parents[1] / "fixtures" / "rag" / "ket_qua_mau.json"
RAW = {
    item["cau_hoi"]["dang"] + "/" + item["cau_hoi"]["muc_do"]: item["cau_hoi"]
    for item in json.loads(SAMPLES.read_text(encoding="utf-8"))
}
MC_RAW, TF_RAW, SA_RAW = RAW["nhieu_lua_chon/Biet"], RAW["dung_sai/Hieu"], RAW["tra_loi_ngan/Van_dung"]
MC, TF, SA = QuestionType.multiple_choice, QuestionType.true_false, QuestionType.short_answer
B, H, VD = Level.biet, Level.hieu, Level.van_dung


def cell(type_: QuestionType, level: Level) -> Cell:
    statements = (B, B, H, H) if type_ is TF else None
    return Cell(1, "toan", 10, "Vectơ", None, type_, level, 1, statements)


def broken(raw: dict, **changes) -> dict:
    raw = copy.deepcopy(raw)
    for key, value in changes.items():
        if value is None:
            raw.pop(key)
        else:
            raw[key] = value
    return raw


def test_level_mapping_round_trips():
    assert LEVEL_FROM_RAG == {"Biet": B, "Hieu": H, "Van_dung": VD}
    assert {LEVEL_FROM_RAG[LEVEL_TO_RAG[lv]] for lv in Level} == set(Level)


def test_multiple_choice_is_normalized():
    question, errors = parse_question(MC_RAW, cell(MC, B))
    assert errors == []
    assert question == {
        "type": "multiple_choice",
        "level": "Biết",
        "stem": MC_RAW["de_bai"],
        "options": ["8", "7,5", "6", "10"],
        "answer": "B",
        "solution": MC_RAW["loi_giai"],
        "citations": ["de_02/PI/C9", "de_01/PI/C7"],
        "check": MC_RAW["kiem_tra"],
    }


def test_true_false_keeps_four_statements():
    question, errors = parse_question(TF_RAW, cell(TF, H))
    assert errors == []
    assert question["type"] == "true_false"
    assert question["answer"] == "SĐSS"
    assert [s["correct"] for s in question["statements"]] == [False, True, False, False]
    assert question["statements"][0]["text"] == TF_RAW["y_dung_sai"][0]["noi_dung"]
    assert question["statements"][0]["explanation"] == TF_RAW["y_dung_sai"][0]["giai_thich"]
    assert "options" not in question


def test_short_answer():
    question, errors = parse_question(SA_RAW, cell(SA, VD))
    assert errors == []
    assert question["answer"] == "7,07"
    assert "options" not in question and "statements" not in question


def test_without_cell_only_structure_is_checked():
    assert parse_question(MC_RAW, None)[1] == []


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("không phải dict", "không phải object"),
        (broken(MC_RAW, dang="tu_luan"), "dạng câu"),
        (broken(MC_RAW, muc_do="Kho"), "mức độ"),
        (broken(MC_RAW, de_bai="  "), "đề bài"),
        (broken(MC_RAW, loi_giai=None), "lời giải"),
        (broken(MC_RAW, phuong_an=["1", "2", "3"]), "4 phương án"),
        (broken(MC_RAW, phuong_an=["1", "2", "", "4"]), "4 phương án"),
        (broken(MC_RAW, dap_an="E"), "A, B, C hoặc D"),
        (broken(TF_RAW, y_dung_sai=TF_RAW["y_dung_sai"][:3]), "4 ý"),
        (broken(TF_RAW, y_dung_sai=[{"noi_dung": "x", "dung": "đúng"}] * 4), "4 ý"),
        (broken(TF_RAW, dap_an="SĐS"), "4 ký tự Đ/S"),
        (broken(TF_RAW, dap_an="ĐĐSS"), "không khớp"),
        (broken(SA_RAW, dap_an=""), "đáp án"),
        (broken(SA_RAW, dap_an="12,345"), "tối đa 4 ký tự"),
        (broken(SA_RAW, dap_an=7.07), "đáp án"),
    ],
)
def test_malformed_question_is_rejected(raw, expected):
    question, errors = parse_question(raw, None)
    assert question is None
    assert any(expected in e for e in errors), errors


def test_question_of_another_type_or_level_than_the_cell_is_rejected():
    assert any("dạng" in e for e in parse_question(MC_RAW, cell(SA, B))[1])
    assert any("mức độ" in e for e in parse_question(MC_RAW, cell(MC, H))[1])


def test_split_moves_malformed_questions_to_rejected_with_reasons():
    bad = broken(MC_RAW, dap_an="Z")
    valid, rejected = split_questions([MC_RAW, bad], cell(MC, B))
    assert [q["answer"] for q in valid] == ["B"]
    assert rejected == [{"question": bad, "errors": ["Đáp án phải là A, B, C hoặc D"]}]


@pytest.mark.parametrize("raw", [MC_RAW, TF_RAW, SA_RAW], ids=["mc", "tf", "sa"])
def test_to_rag_round_trips_a_normalized_question(raw):
    question, _ = parse_question(raw, None)
    assert parse_question(to_rag(question), None) == (question, [])


def test_to_rag_of_a_teacher_edit_is_checked_like_a_rag_question():
    question, _ = parse_question(SA_RAW, None)
    _, errors = parse_question(to_rag(question | {"answer": "12,345"}), cell(SA, VD))
    assert errors == ["Đáp án trả lời ngắn tối đa 4 ký tự (đang là '12,345')"]
    _, errors = parse_question(to_rag({"type": "essay", "level": "Khó", "statements": "x"}), None)
    assert "Không nhận ra dạng câu 'essay'" in errors
    assert "Không nhận ra mức độ 'Khó'" in errors



# ----- bảng trong câu hỏi: một dạng chuẩn = danh sách hàng (hàng đầu là header) -----

BBT_STEM = "Cho hàm số có bảng biến thiên:\n| $x$ | $-\\infty$ | $1$ | $+\\infty$ |\n|---|---|---|---|\n| $y'$ | + | 0 | - |\nHàm số đồng biến trên?"


def T(rows):
    return {"table": rows}


def X(text):
    return {"text": text}


def test_stem_blocks_keeps_order_text_table_text():
    assert stem_blocks({"stem": BBT_STEM}) == [
        X("Cho hàm số có bảng biến thiên:"),
        T([["$x$", "$-\\infty$", "$1$", "$+\\infty$"], ["$y'$", "+", "0", "-"]]),
        X("Hàm số đồng biến trên?"),
    ]


def test_stem_blocks_two_tables_both_kept_in_place():
    stem = "A\n| a | b |\n|---|---|\n| 1 | 2 |\nB\n| c |\n|---|\n| 3 |\nC"
    assert stem_blocks({"stem": stem}) == [X("A"), T([["a", "b"], ["1", "2"]]), X("B"), T([["c"], ["3"]]), X("C")]


def test_stem_blocks_table_field_wins_and_strips_markdown_tables():
    blocks = stem_blocks({"stem": BBT_STEM, "table": [["a", "b"], ["1", "2"]]})
    assert blocks == [X("Cho hàm số có bảng biến thiên:\nHàm số đồng biến trên?"), T([["a", "b"], ["1", "2"]])]


def test_stem_blocks_without_table_is_plain_text():
    assert stem_blocks({"stem": "Tính $|x|$."}) == [X("Tính $|x|$.")]


def test_stem_blocks_pipe_line_without_separator_is_text():
    assert stem_blocks({"stem": "Cho\n|x| = 2 | y\nXong"}) == [X("Cho\n|x| = 2 | y\nXong")]


def test_stem_blocks_alignment_separator():
    assert stem_blocks({"stem": "| a | b |\n|:---:|---:|\n| 1 | 2 |"}) == [T([["a", "b"], ["1", "2"]])]


def test_stem_blocks_edge_pipes_optional():
    assert stem_blocks({"stem": "a | b\n--- | ---\n1 | 2"}) == [T([["a", "b"], ["1", "2"]])]
    assert stem_blocks({"stem": "| a | b\n|---|---\n1 | 2 |"}) == [T([["a", "b"], ["1", "2"]])]


def test_stem_blocks_escaped_pipe_is_literal():
    assert stem_blocks({"stem": "| a \\| b | c |\n|---|---|\n| 1 | 2 |"}) == [T([["a | b", "c"], ["1", "2"]])]


def test_stem_blocks_pipes_inside_inline_and_display_math():
    stem = "| $|x|$ | $$|y|+1$$ |\n|---|---|\n| a | b |"
    assert stem_blocks({"stem": stem}) == [T([["$|x|$", "$$|y|+1$$"], ["a", "b"]])]


# ----- hình khối: figure_spec (hinh_ve), tham số hình do LLM trả -----

SPEC = {"solid": "pyramid", "a": 3, "b": 4, "h": 5, "foot": "center"}


def test_figure_spec_is_kept_when_present():
    question, errors = parse_question(broken(MC_RAW, hinh_ve=SPEC), cell(MC, B))
    assert errors == []
    assert question["figure_spec"] == SPEC


@pytest.mark.parametrize("empty", [None, {}])
def test_empty_figure_spec_is_left_out(empty):
    question, _ = parse_question(MC_RAW | {"hinh_ve": empty}, cell(MC, B))
    assert "figure_spec" not in question


def test_question_without_figure_spec_has_no_such_key():
    question, _ = parse_question(MC_RAW, cell(MC, B))
    assert "figure_spec" not in question and "figure_svg" not in question


def test_figure_spec_goes_back_to_rag_when_the_teacher_edits():
    question, _ = parse_question(broken(MC_RAW, hinh_ve=SPEC), cell(MC, B))
    assert to_rag(question)["hinh_ve"] == SPEC


def test_the_derived_svg_never_goes_back_to_rag():
    assert "figure_svg" not in str(to_rag({**parse_question(MC_RAW, cell(MC, B))[0], "figure_svg": "<svg/>"}))
