"""Tóm tắt: unit test bộ cắt đề thi (T-004, TC-005): mỗi câu một đoạn có phương án, ý a–d, hình/bảng và đáp án chính thức; ID ổn định và không trùng giữa các đề; thêm trường hợp biên với đề JSON tự dựng."""

import json
from collections import Counter

import pytest

from app.rag.chunking.exam import chunk_exam, exam_item_id
from tests.rag.support import ALL_EXAMS, EXAM_2025, EXAM_2026, EXAM_REF_2025

# --- existing behaviour (T-004) --------------------------------------------------------------------------------

def test_TC_005_toan_exam_chunks_into_22_items():
    chunks = chunk_exam(EXAM_2025)

    assert len(chunks) == 22
    assert all(c.kind == "exam_item" for c in chunks)
    assert Counter(c.part for c in chunks) == {"I": 12, "II": 4, "III": 6}
    for c in chunks:
        assert (c.year, c.exam_code, c.official, c.subject) == (2025, "0101", True, "toan")
        assert c.topic
        assert "Đáp án:" in c.text
    for c in chunks:
        if c.part == "I":
            assert all(f"\n{x}. " in c.text for x in "ABCD")
        if c.part == "II":
            assert all(f"\n{x}) " in c.text for x in "abcd")
    # Official answers from the Bộ GD&ĐT key: Câu 1 Phần I = C, Câu 1 Phần III = 1260.
    by_no = {(c.part, c.question_no): c for c in chunks}
    assert by_no[("I", 1)].text.endswith("Đáp án: C")
    assert by_no[("III", 1)].text.endswith("Đáp án: 1260")


def test_true_false_chunk_holds_all_4_statements_and_answers():
    q = next(c for c in chunk_exam(EXAM_2025) if c.part == "II" and c.question_no == 1)

    # Official key 0101 Phần II Câu 1: Đ S S S
    assert "a) Hàm số đã cho có đạo hàm là $f'(x)=3x^2-12$." in q.text
    assert all(f"\n{x}) " in q.text for x in "abcd")
    assert q.text.endswith("Đáp án: a) Đúng, b) Sai, c) Sai, d) Sai")


def test_chunk_ids_are_unique_and_stable():
    first = [c.id for c in chunk_exam(EXAM_2025)]

    assert len(set(first)) == 22
    assert first == [c.id for c in chunk_exam(EXAM_2025)]


def test_reference_exam_chunks_into_22_items():
    chunks = chunk_exam(EXAM_REF_2025)

    # Bộ GD&ĐT đề tham khảo 2025 (18/10/2024): one paper, official key.
    assert Counter(c.part for c in chunks) == {"I": 12, "II": 4, "III": 6}
    assert all((c.year, c.exam_code, c.official) == (2025, "tham-khao", True) and c.topic for c in chunks)
    by_no = {(c.part, c.question_no): c for c in chunks}
    assert by_no[("I", 1)].text.endswith("Đáp án: B")
    assert by_no[("II", 4)].text.endswith("Đáp án: a) Đúng, b) Sai, c) Đúng, d) Đúng")
    assert by_no[("III", 6)].text.endswith("Đáp án: 0,08")


# --- every committed exam --------------------------------------------------------------------------------------

@pytest.mark.parametrize("path", ALL_EXAMS, ids=lambda p: p.stem)
def test_every_fixture_exam_has_the_official_22_item_structure(path):
    chunks = chunk_exam(path)

    assert Counter(c.part for c in chunks) == {"I": 12, "II": 4, "III": 6}
    assert [c.question_no for c in chunks if c.part == "I"] == list(range(1, 13))
    assert all(c.text.startswith(f"Câu {c.question_no}. ") for c in chunks)
    assert all(c.heading_path.endswith(f"> Phần {c.part} > Câu {c.question_no}") for c in chunks)
    assert all(c.source == path.name and c.page is None and c.grade == 12 for c in chunks)


def test_2026_exam_carries_its_year_and_code():
    assert {(c.year, c.exam_code) for c in chunk_exam(EXAM_2026)} == {(2026, "0102")}


def test_ids_never_collide_across_the_three_exams():
    ids = [c.id for path in ALL_EXAMS for c in chunk_exam(path)]

    assert len(ids) == 66 and len(set(ids)) == 66


def test_every_part_iii_answer_fits_the_answer_sheet():
    for path in ALL_EXAMS:
        for c in chunk_exam(path):
            if c.part == "III":
                answer = c.text.rsplit("Đáp án: ", 1)[1]
                assert len(answer) <= 4, (path.name, c.question_no, answer)


# --- edge cases with a hand-made exam --------------------------------------------------------------------------

def _exam(tmp_path, questions, name="de.json", **over):
    data = {"exam": "Đề thi tốt nghiệp THPT 2024", "ma_de": "999", "subject": "toan", "official": False,
            "questions": questions} | over
    path = tmp_path / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


MC = {"part": "I", "cau": 1, "stem": "Chọn đáp án đúng.", "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
      "answer": "B", "topic": "dai_so_giai_tich/dao_ham"}


def test_figure_and_table_are_written_before_the_options(tmp_path):
    q = MC | {"figure": "Hình chóp $S.ABCD$", "table": [["x", "1", "2"], ["y", "3", "4"]]}

    [c] = chunk_exam(_exam(tmp_path, [q]))

    assert c.text.splitlines() == ["Câu 1. Chọn đáp án đúng.", "Hình: Hình chóp $S.ABCD$", "| x | 1 | 2 |",
                                   "|---|---|---|", "| y | 3 | 4 |", "A. 1", "B. 2", "C. 3", "D. 4", "Đáp án: B"]


def test_a_table_with_only_a_header_row_still_renders(tmp_path):
    [c] = chunk_exam(_exam(tmp_path, [MC | {"table": [["a", "b"]]}]))

    assert "| a | b |\n|---|---|\nA. 1" in c.text


def test_year_and_official_flag_come_from_the_file(tmp_path):
    [c] = chunk_exam(_exam(tmp_path, [MC]))

    assert (c.year, c.exam_code, c.official, c.topic, c.part) == (2024, "999", False, "dai_so_giai_tich/dao_ham", "I")
    assert c.heading_path == "Toán TN 2024 mã 999 > Phần I > Câu 1"


def test_the_same_exam_under_another_file_name_gets_other_ids(tmp_path):
    a = chunk_exam(_exam(tmp_path, [MC], name="a.json"))
    b = chunk_exam(_exam(tmp_path, [MC], name="b.json"))

    assert a[0].id != b[0].id and a[0].text == b[0].text


def test_exam_item_id_depends_on_file_part_and_question_only():
    assert exam_item_id("de.json", "I", 1) == exam_item_id("de.json", "I", 1)
    assert len({exam_item_id("de.json", p, n) for p in ("I", "II", "III") for n in range(1, 13)}) == 36
    assert len(exam_item_id("de.json", "I", 1)) == 16


def test_true_false_answers_are_written_in_vietnamese(tmp_path):
    tf = {"part": "II", "cau": 1, "stem": "Xét tính đúng sai.", "topic": "dai_so_giai_tich/dao_ham",
          "statements": [{"label": x, "text": f"ý {x}", "answer": x in "ac"} for x in "abcd"]}

    [c] = chunk_exam(_exam(tmp_path, [tf]))

    assert c.text.endswith("Đáp án: a) Đúng, b) Sai, c) Đúng, d) Sai")
    assert "A. " not in c.text


def test_an_exam_with_no_questions_gives_no_chunks(tmp_path):
    assert chunk_exam(_exam(tmp_path, [])) == []


def test_chunk_order_follows_the_file(tmp_path):
    qs = [MC | {"part": "III", "cau": 2, "answer": "5"}, MC | {"cau": 7}, MC | {"part": "II", "cau": 1}]

    assert [(c.part, c.question_no) for c in chunk_exam(_exam(tmp_path, qs))] == [("III", 2), ("I", 7), ("II", 1)]


def test_accepts_a_string_path(tmp_path):
    assert len(chunk_exam(str(_exam(tmp_path, [MC])))) == 1


def _school_exam(tmp_path, **extra):
    exam = {"id": "x", "exam": "Đề kiểm tra cuối kì 1 Toán 10 năm 2025", "subject": "toan", "ma_de": "01",
            "official": False, "questions": [{"part": "I", "cau": 1, "topic": "dai_so_giai_tich/luong_giac",
                                             "stem": "s", "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                                             "answer": "A"}], **extra}
    path = tmp_path / "school.json"
    path.write_text(json.dumps(exam, ensure_ascii=False), encoding="utf-8")
    return path


def test_grade_defaults_to_12_for_graduation_exams():
    assert {c.grade for c in chunk_exam(EXAM_2025)} == {12}


def test_grade_is_read_from_the_exam_file(tmp_path):
    chunks = chunk_exam(_school_exam(tmp_path, grade=10, heading="Toán 10 CK1 2025 đề 01"))

    assert chunks[0].grade == 10
    assert chunks[0].heading_path == "Toán 10 CK1 2025 đề 01 > Phần I > Câu 1"


def test_grade_parameter_overrides_the_file(tmp_path):
    assert chunk_exam(_school_exam(tmp_path, grade=10), grade=11)[0].grade == 11


def test_exam_without_a_year_in_its_title_has_no_year(tmp_path):
    chunks = chunk_exam(_school_exam(tmp_path, exam="Đề kiểm tra cuối kì 1 Toán 11 – Đề số 01", grade=11, heading="h"))

    assert chunks[0].year is None


# --- T-034: question type and level metadata -------------------------------------------------------------------

def test_every_item_carries_the_question_type_of_its_part():
    types = {c.part: c.type for c in chunk_exam(EXAM_2025)}

    assert types == {"I": "multiple_choice", "II": "true_false", "III": "short_answer"}


def test_level_and_statement_levels_are_kept_when_the_source_has_them(tmp_path):
    tf = {"part": "II", "cau": 1, "stem": "Cho $f(x)=x^2$.", "topic": "dai_so_giai_tich/dao_ham", "level": "Hiểu",
          "statement_levels": ["Biết", "Biết", "Hiểu", "Hiểu"],
          "statements": [{"label": x, "text": f"ý {x}", "answer": True} for x in "abcd"]}

    mc, item = chunk_exam(_exam(tmp_path, [MC | {"level": "Biết"}, tf]))

    assert (mc.level, mc.statement_levels) == ("Biết", None)
    assert (item.level, item.statement_levels) == ("Hiểu", ["Biết", "Biết", "Hiểu", "Hiểu"])


def test_items_without_a_level_have_none(tmp_path):
    [c] = chunk_exam(_exam(tmp_path, [MC]))

    assert c.level is None and c.exam_kind is None


def test_type_by_part_is_vocab_part_by_type_inverted():
    from app.rag.chunking.exam import TYPE_BY_PART
    from app.rag.vocab import PART_BY_TYPE

    assert TYPE_BY_PART == {part: t for t, part in PART_BY_TYPE.items()}


# --- T-055, TC-027: đề trường không có mã đề hay năm -------------------------------------------------------------

def test_TC_027_school_exam_without_ma_de_is_chunked(tmp_path):
    """Đề kiểm tra của trường thường không có mã đề; trước đây chunk_exam báo KeyError('ma_de') lúc nạp."""
    path = _school_exam(tmp_path, exam="Đề kiểm tra giữa kì 2 Vật lí 12 năm 2026", subject="ly")
    exam = json.loads(path.read_text(encoding="utf-8"))
    exam.pop("ma_de")
    path.write_text(json.dumps(exam, ensure_ascii=False), encoding="utf-8")

    [chunk] = chunk_exam(path)
    assert chunk.exam_code is None


def test_TC_027_exam_without_a_year_is_labelled_by_its_title(tmp_path):
    chunks = chunk_exam(_school_exam(tmp_path, exam="Đề kiểm tra giữa kì 2 Vật lí 12 trường X", subject="ly"))

    assert chunks[0].heading_path.startswith("Đề kiểm tra giữa kì 2 Vật lí 12 trường X > Phần I")
    assert "None" not in chunks[0].heading_path


def test_TC_027_exam_without_ma_de_is_labelled_by_its_title(tmp_path):
    path = _school_exam(tmp_path, exam="Đề thi thử Vật lí 2026 trường X", subject="ly")
    exam = json.loads(path.read_text(encoding="utf-8"))
    exam["ma_de"] = ""
    path.write_text(json.dumps(exam, ensure_ascii=False), encoding="utf-8")

    assert chunk_exam(path)[0].heading_path.startswith("Đề thi thử Vật lí 2026 trường X > Phần I")


def test_TC_027_graduation_exam_label_is_unchanged():
    assert chunk_exam(EXAM_2025)[0].heading_path.startswith("Toán TN 2025 mã 0101 > Phần I")
