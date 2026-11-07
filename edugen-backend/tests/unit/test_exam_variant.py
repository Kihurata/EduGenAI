"""Mã đề: cùng đề, thứ tự câu và phương án khác nhau theo mã, đáp án đúng luôn theo nội dung.

Đầu ra mong muốn:
- Cùng (đề, mã đề) luôn ra cùng thứ tự; mã khác nhau ra thứ tự khác nhau.
- Câu chỉ đổi chỗ trong phần của nó; không mất, không thêm câu; đầu vào không bị sửa.
- Câu nhiều lựa chọn: nội dung phương án đúng không đổi dù chữ cái đổi.
- Câu nhắc phương án/chữ cái/câu khác thì giữ nguyên thứ tự (xáo sẽ làm đề sai nghĩa).
"""

import copy
import uuid

import pytest

from app.domain.exam_document import ExamInfo, build_blocks, to_markdown
from app.domain.exam_variant import is_valid_code, make_variant, options_pinned, variant_seed
from app.domain.question import OPTION_LETTERS
from app.models.enums import ExportVariant

EXAM_ID = uuid.UUID(int=1)
INFO = ExamInfo("THPT Nguyễn Du", "KTGK", "Toán", 10, 45)


def mc(n: int, **extra) -> dict:
    options = [f"đáp án-{n}-{k}" for k in OPTION_LETTERS]
    return {
        "type": "multiple_choice", "level": "Biết", "stem": f"Đề {n}", "options": options,
        "answer": "B", "solution": f"Vì {n} nên đúng.", "citations": [], "check": None,
    } | extra  # fmt: skip


def tf(n: int) -> dict:
    statements = [{"text": f"ý {k} của {n}", "correct": k in "ac", "explanation": ""} for k in "abcd"]
    return {
        "type": "true_false", "level": "Hiểu", "stem": f"Đề đúng sai {n}", "statements": statements,
        "answer": "ĐSĐS", "solution": "gi", "citations": [], "check": None,
    }  # fmt: skip


def sa(n: int) -> dict:
    return {
        "type": "short_answer", "level": "Vận dụng", "stem": f"Đề trả lời ngắn {n}", "answer": str(n),
        "solution": "gi", "citations": [], "check": None,
    }  # fmt: skip


QUESTIONS = [*(mc(n) for n in range(1, 13)), *(tf(n) for n in range(1, 5)), *(sa(n) for n in range(1, 7))]


def correct_text(q: dict) -> str:
    return q["options"][OPTION_LETTERS.index(q["answer"])]


def stems(qs: list[dict], type_: str) -> list[str]:
    return [q["stem"] for q in qs if q["type"] == type_]


def test_same_exam_and_code_is_reproducible_other_code_differs():
    a = make_variant(QUESTIONS, variant_seed(EXAM_ID, "101"))
    assert a == make_variant(QUESTIONS, variant_seed(EXAM_ID, "101"))
    assert a != make_variant(QUESTIONS, variant_seed(EXAM_ID, "102"))
    assert variant_seed(EXAM_ID, "101") != variant_seed(uuid.UUID(int=2), "101")


def test_no_question_lost_and_input_untouched():
    snapshot = copy.deepcopy(QUESTIONS)
    out = make_variant(QUESTIONS, variant_seed(EXAM_ID, "101"))
    assert QUESTIONS == snapshot
    assert sorted(q["stem"] for q in out) == sorted(q["stem"] for q in QUESTIONS)
    by_stem = {q["stem"]: q for q in QUESTIONS}
    for q in out:  # ngoài thứ tự phương án, mỗi câu giữ nguyên
        assert {k: v for k, v in q.items() if k not in ("options", "answer")} == {
            k: v for k, v in by_stem[q["stem"]].items() if k not in ("options", "answer")
        }


@pytest.mark.parametrize("code", ["101", "102", "103", "A", "mã9"])
def test_correct_option_text_survives_shuffle(code):
    out = make_variant(QUESTIONS, variant_seed(EXAM_ID, code))
    original = {q["stem"]: q for q in QUESTIONS}
    for q in out:
        if q["type"] == "multiple_choice":
            assert sorted(q["options"]) == sorted(original[q["stem"]]["options"])
            assert correct_text(q) == correct_text(original[q["stem"]])


def test_shuffle_actually_moves_questions_and_options():
    out = make_variant(QUESTIONS, variant_seed(EXAM_ID, "101"))
    assert stems(out, "multiple_choice") != stems(QUESTIONS, "multiple_choice")
    assert any(q["options"] != o["options"] for q, o in zip(sorted(out, key=lambda q: q["stem"]),
                                                          sorted(QUESTIONS, key=lambda q: q["stem"])))  # fmt: skip


def test_true_false_statements_keep_their_order():
    out = make_variant(QUESTIONS, variant_seed(EXAM_ID, "101"))
    original = {q["stem"]: q for q in QUESTIONS}
    for q in out:
        if q["type"] == "true_false":
            assert q["statements"] == original[q["stem"]]["statements"]


@pytest.mark.parametrize(
    "extra",
    [
        {"options": ["A và B đều đúng", "x", "y", "z"]},
        {"options": ["Cả A và B", "x", "y", "z"]},
        {"options": ["Cả ba phương án trên", "x", "y", "z"]},
        {"options": ["Tất cả các phương án đều đúng", "x", "y", "z"]},
        {"options": ["Không có đáp án nào đúng", "x", "y", "z"]},
        {"solution": "Vậy chọn B."},
        {"solution": "Đáp án C là đúng."},
        {"solution": "Phương án A sai vì ..."},
    ],
)
def test_option_order_pinned_when_content_depends_on_letters(extra):
    q = mc(1, **extra)
    assert options_pinned(q)
    [out] = make_variant([q], 12345)
    assert (out["options"], out["answer"]) == (q["options"], q["answer"])


def test_plain_math_options_and_solutions_are_not_pinned():
    q = mc(1, options=["$x = 1$", "tất cả các số thực", "$A = B$", "$AB = 2$"], solution="Điểm $A$ và $B$ nằm trên đường thẳng.")
    assert not options_pinned(q)


def test_questions_referring_to_others_keep_part_order():
    qs = [mc(n) for n in range(1, 9)]
    qs[3] = mc(4, stem="Dựa vào kết quả câu trước, tính ...")
    assert stems(make_variant(qs, 7), "multiple_choice") == [q["stem"] for q in qs]
    qs[3] = mc(4, stem="Cho hàm số như câu 2.")
    assert stems(make_variant(qs, 7), "multiple_choice") == [q["stem"] for q in qs]


def test_one_part_pinned_does_not_pin_other_parts():
    qs = [mc(n) for n in range(1, 4)] + [sa(n) for n in range(1, 9)]
    qs[0] = mc(1, stem="Xét câu trước đó")
    out = make_variant(qs, 7)
    assert stems(out, "multiple_choice") == stems(qs, "multiple_choice")
    assert stems(out, "short_answer") != stems(qs, "short_answer")


def test_document_answer_key_follows_the_shuffled_options():
    out = make_variant(QUESTIONS, variant_seed(EXAM_ID, "101"))
    md = to_markdown(build_blocks(INFO, out, ExportVariant.teacher))
    mc_out = [q for q in out if q["type"] == "multiple_choice"]
    row = next(line for line in md.splitlines() if line.startswith("| Đáp án |"))
    assert row == "| Đáp án | " + " | ".join(q["answer"] for q in mc_out) + " |"


def test_code_is_printed_only_when_given():
    assert "Mã đề" not in to_markdown(build_blocks(INFO, QUESTIONS, ExportVariant.student))
    coded = ExamInfo("THPT Nguyễn Du", "KTGK", "Toán", 10, 45, code="101")
    assert "**Mã đề: 101**" in to_markdown(build_blocks(coded, QUESTIONS, ExportVariant.student))


@pytest.mark.parametrize("code", ["1", "101", "A1b2", "12345678"])
def test_valid_codes(code):
    assert is_valid_code(code)


@pytest.mark.parametrize("code", ["", "123456789", "10 1", "10/1", "../1", "mã đề", "1\n"])
def test_invalid_codes(code):
    assert not is_valid_code(code)
