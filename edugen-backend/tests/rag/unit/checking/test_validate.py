"""Tóm tắt: unit test bước kiểm tra định dạng câu (T-009, TC-006): trích dẫn phải có và nằm trong đoạn đã truy xuất, trắc nghiệm đủ A–D, Đ/S đủ 4 ý a–d đúng/sai, đáp án Phần III vừa 4 ô phiếu; thêm biên của phiếu trả lời, nhiều lỗi cùng lúc, câu sửa tay của giáo viên và dữ liệu xấu."""

import pytest

from app.rag.checking.validate import validate

RETRIEVED = {"c1", "c2"}


def _mc(**over):
    q = {"type": "multiple_choice", "stem": "Đạo hàm của $x^2$ là", "options": {"A": "$2x$", "B": "$x$", "C": "$2$", "D": "$x^2$"},
         "answer": "A", "explanation": "...", "level": "Biết", "topic": "dao_ham", "source_chunk_ids": ["c1"]}
    return q | over


def _tf(**over):
    q = {"type": "true_false", "stem": "Cho $f(x)=x^3$.",
         "statements": [{"label": x, "text": f"ý {x}", "answer": True} for x in "abcd"],
         "explanation": "...", "level": "Hiểu", "topic": "dao_ham", "source_chunk_ids": ["c2"]}
    return q | over


def _short(answer, **over):
    q = {"type": "short_answer", "stem": "Tính ...", "answer": answer, "explanation": "...", "level": "Vận dụng",
         "topic": "dao_ham", "source_chunk_ids": ["c1", "c2"]}
    return q | over


# --- existing behaviour ----------------------------------------------------------------------------------------

def test_valid_questions_have_no_errors():
    assert validate(_mc(), RETRIEVED) == []
    assert validate(_tf(), RETRIEVED) == []
    assert validate(_short("12"), RETRIEVED) == []


def test_TC_006_part3_answer_fits_4_boxes():
    for ok in ["12", "-1,5", "0,25", "1234"]:
        assert validate(_short(ok), RETRIEVED) == [], ok
    for too_long in ["12,34", "-123,4"]:
        assert validate(_short(too_long), RETRIEVED) != [], too_long


@pytest.mark.parametrize("answer", ["1.5", "1/2", "", "a"])
def test_part3_answer_uses_only_digits_minus_and_comma(answer):
    # Answer sheet columns only have -, ",", 0–9 (CV 1239/BGDĐT-QLCL, see "Dữ liệu đầu vào hệ thống").
    assert validate(_short(answer), RETRIEVED) != []


def test_citing_a_chunk_that_was_not_retrieved_is_rejected():
    errors = validate(_mc(source_chunk_ids=["c1", "zzz"]), RETRIEVED)

    assert any("zzz" in e for e in errors)


def test_question_without_citation_is_rejected():
    assert validate(_mc(source_chunk_ids=[]), RETRIEVED) != []


@pytest.mark.parametrize("over", [
    {"options": {"A": "1", "B": "2", "C": "3"}},
    {"options": {"A": "1", "B": "2", "C": "3", "D": "4", "E": "5"}},
    {"options": {"A": "1", "B": "2", "C": "3", "E": "4"}},
    {"answer": "E"},
])
def test_multiple_choice_needs_options_a_to_d_and_answer_in_them(over):
    assert validate(_mc(**over), RETRIEVED) != []


@pytest.mark.parametrize("n", [3, 5])
def test_true_false_needs_exactly_4_statements(n):
    statements = [{"label": x, "text": "ý", "answer": False} for x in "abcde"[:n]]

    assert validate(_tf(statements=statements), RETRIEVED) != []


def test_true_false_statement_answers_must_be_booleans():
    statements = [{"label": x, "text": "ý", "answer": "Đúng"} for x in "abcd"]

    assert validate(_tf(statements=statements), RETRIEVED) != []


def test_validate_without_retrieved_ids_for_teacher_edits():
    """T-028: a teacher edit has no retrieval run, so only the citation's presence is checked."""
    assert validate(_mc(source_chunk_ids=["any-chunk"]), None) == []
    assert validate(_mc(source_chunk_ids=[]), None) == ["no source_chunk_ids"]


# --- exact messages (the teacher sees them as-is, D-008) -------------------------------------------------------

@pytest.mark.parametrize("q, message", [
    (_mc(source_chunk_ids=[]), "no source_chunk_ids"),
    (_mc(source_chunk_ids=["zz"]), "cites chunk zz that was not retrieved"),
    (_mc(options={"A": "1"}), "multiple_choice needs exactly options A, B, C, D"),
    (_mc(answer="E"), "multiple_choice answer 'E' is not A–D"),
    (_tf(statements=[]), "true_false needs exactly 4 statements a, b, c, d"),
    (_short("1.5"), "short_answer '1.5' is not a number written with digits, '-' and ','"),
    (_short("12345"), "short_answer '12345' does not fit the 4 answer-sheet boxes"),
    (_mc(type="essay"), "unknown question type 'essay'"),
])
def test_error_messages(q, message):
    assert message in validate(q, RETRIEVED)


# --- answer-sheet edge cases (Phần III) ------------------------------------------------------------------------

@pytest.mark.parametrize("answer", ["0", "-0", "9999", "-999", "0,5", "-0,5", "1,25", "99,9"])
def test_answers_the_4_box_sheet_can_hold(answer):
    assert validate(_short(answer), RETRIEVED) == []


@pytest.mark.parametrize("answer", ["10000", "-1234", "0,125", "-0,25", "12,5,"])
def test_answers_longer_than_4_boxes(answer):
    assert validate(_short(answer), RETRIEVED) != []


@pytest.mark.parametrize("answer", ["+5", " 12", "12 ", ",5", "5,", "1,2,3", "--1", "1e3", "½"])
def test_answers_the_sheet_cannot_write(answer):
    assert validate(_short(answer), RETRIEVED) != []


@pytest.mark.parametrize("answer", ["١٢", "１２"])
def test_only_ascii_digits_fit_the_sheet(answer):
    assert validate(_short(answer), RETRIEVED) != []


@pytest.mark.parametrize("answer", [12, 1.5, None, ["1"]])
def test_short_answer_must_be_a_string(answer):
    assert validate(_short(answer), RETRIEVED) != []


# --- multiple choice and true/false edge cases ----------------------------------------------------------------

def test_option_order_does_not_matter():
    assert validate(_mc(options={"D": "4", "C": "3", "B": "2", "A": "1"}), RETRIEVED) == []


@pytest.mark.parametrize("answer", ["a", "", None, "AB", " A"])
def test_multiple_choice_answer_must_be_one_capital_letter(answer):
    assert validate(_mc(answer=answer), RETRIEVED) != []


def test_true_false_labels_must_be_in_order():
    statements = [{"label": x, "text": "ý", "answer": True} for x in "bacd"]

    assert validate(_tf(statements=statements), RETRIEVED) != []


@pytest.mark.parametrize("answer", [1, 0, None, "true"])
def test_true_false_answers_must_be_real_booleans(answer):
    statements = [{"label": x, "text": "ý", "answer": answer} for x in "abcd"]

    assert validate(_tf(statements=statements), RETRIEVED) != []


def test_mixed_true_and_false_statements_are_fine():
    statements = [{"label": x, "text": "ý", "answer": x in "bd"} for x in "abcd"]

    assert validate(_tf(statements=statements), RETRIEVED) == []


# --- citations -------------------------------------------------------------------------------------------------

def test_every_uncited_chunk_is_reported():
    errors = validate(_mc(source_chunk_ids=["x", "c1", "y"]), RETRIEVED)

    assert errors == ["cites chunk x that was not retrieved", "cites chunk y that was not retrieved"]


def test_an_empty_retrieval_rejects_every_citation():
    assert validate(_mc(), set()) == ["cites chunk c1 that was not retrieved"]


@pytest.mark.parametrize("ids", [None, []])
def test_missing_or_empty_citations_read_the_same(ids):
    assert validate(_mc(source_chunk_ids=ids), RETRIEVED) == ["no source_chunk_ids"]


def test_a_question_with_no_citation_key_at_all():
    q = _mc()
    del q["source_chunk_ids"]

    assert validate(q, RETRIEVED) == ["no source_chunk_ids"]


# --- several errors at once ------------------------------------------------------------------------------------

def test_errors_from_every_rule_are_collected():
    errors = validate(_mc(source_chunk_ids=[], options={"A": "1"}, answer="E"), RETRIEVED)

    assert errors == ["no source_chunk_ids", "multiple_choice needs exactly options A, B, C, D",
                      "multiple_choice answer 'E' is not A–D"]


def test_a_question_without_a_type_is_rejected():
    q = _mc()
    del q["type"]

    assert validate(q, RETRIEVED) == ["unknown question type None"]


def test_validate_does_not_change_the_question():
    q = _tf()
    before = repr(q)

    validate(q, RETRIEVED)

    assert repr(q) == before


# --- bad data (teacher edits arrive over HTTP, D-010) ----------------------------------------------------------

def test_null_options_are_an_error_not_a_crash():
    assert validate(_mc(options=None), RETRIEVED) != []


def test_null_statements_are_an_error_not_a_crash():
    assert validate(_tf(statements=None), RETRIEVED) != []


# --- stress ----------------------------------------------------------------------------------------------------

def test_every_4_box_integer_from_minus_999_to_9999_is_valid():
    assert all(validate(_short(str(n)), None) == [] for n in range(-999, 10000))
