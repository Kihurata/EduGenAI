"""Tóm tắt: unit test bộ sinh câu (T-008, T-030) với LLM giả: đọc câu trả lời thành câu hỏi gắn dạng/mức độ/chủ đề của ô, prompt có ID đoạn đã truy xuất và 1–2 câu đề mẫu cùng phần, schema đúng dạng câu, hình/bảng tùy chọn, mức độ từng ý Đ/S; thêm biên (trả rỗng, LLM tự đổi dạng câu, không có đoạn nào) và áp lực."""

import json

import pytest

from app.rag.checking.validate import validate
from app.rag.dto import Chunk
from app.rag.generation.generate import NO_RAG_SYSTEM_PROMPT, SCHEMAS, SYSTEM_PROMPT, build_prompt, generate
from app.rag.generation.llm import LLMError
from tests.rag.fakes import FakeLLM
from tests.rag.support import LLM_OUTPUT, cell, reply

TYPES = ["multiple_choice", "true_false", "short_answer"]


def _theory(i):
    return Chunk(id=f"t{i}", kind="theory", text=f"Toán 12 > Bài 1 > Mục {i}\nNội dung {i}", subject="toan", grade=12,
                 chapter="Chương I", lesson="Bài 1", section=f"Mục {i}", heading_path=f"Toán 12 > Bài 1 > Mục {i}",
                 source="sgk.pdf", page=i, official=True)


def _exam(i, part):
    return Chunk(id=f"ex{part}{i}", kind="exam_item", text=f"Câu {i}. Đề mẫu phần {part}\nĐáp án: ...", subject="toan",
                 grade=12, chapter="", lesson="", section="", heading_path=f"Phần {part} > Câu {i}", source="de.json",
                 page=None, official=True, year=2025, exam_code="0101", part=part, question_no=i, topic="dao_ham")


THEORY = [_theory(1), _theory(2)]
EXAMS = [_exam(1, "I"), _exam(2, "I"), _exam(3, "I"), _exam(1, "II")]
RETRIEVED = {c.id for c in THEORY}


def _cell(qtype, count=1, **extra):
    return cell(qtype, count=count, topic="dao_ham", **extra)


def _generate(qtype, *questions, **cell_extra):
    llm = FakeLLM([reply(*questions)])
    return generate(_cell(qtype, **cell_extra), THEORY, EXAMS, llm), llm


# --- existing behaviour ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("qtype", TYPES)
def test_fake_llm_json_parses_into_valid_question_of_each_type(qtype):
    [q], llm = _generate(qtype, LLM_OUTPUT[qtype])

    assert (q["type"], q["level"], q["topic"]) == (qtype, "Biết", "dao_ham")
    assert validate(q, RETRIEVED) == []
    assert llm.calls[0]["schema"] == SCHEMAS[qtype]


def test_prompt_has_retrieved_chunk_ids_and_1_to_2_exam_items_of_same_part():
    llm = FakeLLM([reply(*[LLM_OUTPUT["multiple_choice"]] * 3)])

    generate(_cell("multiple_choice", count=3), THEORY, EXAMS, llm)

    prompt = llm.calls[0]["prompt"]
    assert "t1" in prompt and "t2" in prompt
    shown = [e for e in EXAMS if e.text in prompt]
    assert 1 <= len(shown) <= 2 and all(e.part == "I" for e in shown)
    assert "3" in prompt and "Biết" in prompt


def test_system_prompt_is_fixed_so_it_can_be_cached():
    systems = {_generate(qtype, LLM_OUTPUT[qtype])[1].calls[0]["system"] for qtype in TYPES}

    assert systems == {SYSTEM_PROMPT}


def test_schemas_only_use_structured_output_features():
    # Structured outputs need additionalProperties: false on every object and reject length/count/pattern limits.
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node["required"]) == set(node["properties"])
            assert not {"minLength", "maxLength", "minItems", "maxItems", "pattern"} & set(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for schema in SCHEMAS.values():
        walk(schema)


@pytest.mark.parametrize("raw", ["not json", "{}", '{"items": []}', "[]", ""])
def test_unreadable_llm_reply_becomes_llm_error(raw):
    """T-028: a reply that is not JSON or has no questions reaches the Backend as LLMError, not a parse error."""
    with pytest.raises(LLMError):
        generate(_cell("multiple_choice"), THEORY, EXAMS, FakeLLM([raw] * 3))


TF_LEVELS = ["Biết", "Hiểu", "Hiểu", "Vận dụng"]


def test_true_false_statement_levels_reach_prompt_and_tag_each_statement():
    """T-028 point 4: a true_false cell may set the level of statements a–d; the question level stays the highest."""
    [q], llm = _generate("true_false", LLM_OUTPUT["true_false"], level="Vận dụng", statement_levels=TF_LEVELS)

    assert "a) Biết, b) Hiểu, c) Hiểu, d) Vận dụng" in llm.calls[0]["prompt"]
    assert [s["level"] for s in q["statements"]] == TF_LEVELS
    assert q["level"] == "Vận dụng"


def test_true_false_without_statement_levels_is_unchanged():
    [q], llm = _generate("true_false", LLM_OUTPUT["true_false"])

    assert "Mức độ từng ý" not in llm.calls[0]["prompt"]
    assert all("level" not in s for s in q["statements"])


# T-030: optional figure description and data table, same shape as the contract fixture.
FIGURE = "Hình lăng trụ $ABC.A'B'C'$, các cạnh bên vuông góc với đáy, $AB=3$."
TABLE = [["Nhóm", "[0;40)", "[40;80)"], ["Tần số", "11", "10"]]


@pytest.mark.parametrize("qtype", TYPES)
def test_schema_has_nullable_figure_and_table(qtype):
    item = SCHEMAS[qtype]["properties"]["questions"]["items"]
    assert {"figure", "table"} <= set(item["required"])
    assert item["properties"]["figure"] == {"anyOf": [{"type": "string"}, {"type": "null"}]}
    assert item["properties"]["table"] == {"anyOf": [
        {"type": "array", "items": {"type": "array", "items": {"type": "string"}}}, {"type": "null"}]}


def test_prompt_asks_for_figure_and_table_only_when_needed():
    _, llm = _generate("multiple_choice", LLM_OUTPUT["multiple_choice"])

    text = llm.calls[0]["system"] + llm.calls[0]["prompt"]
    assert "figure" in text and "table" in text and "null" in text


@pytest.mark.parametrize("qtype", TYPES)
def test_null_figure_and_table_are_dropped(qtype):
    [q], _ = _generate(qtype, LLM_OUTPUT[qtype] | {"figure": None, "table": None})

    assert "figure" not in q and "table" not in q


def test_figure_and_table_are_kept_and_question_still_valid():
    [q], _ = _generate("short_answer", LLM_OUTPUT["short_answer"] | {"figure": FIGURE, "table": TABLE})

    assert (q["figure"], q["table"]) == (FIGURE, TABLE)
    assert validate(q, RETRIEVED) == []


# --- reply edge cases ------------------------------------------------------------------------------------------

def test_an_empty_question_list_is_not_an_error():
    questions, _ = _generate("multiple_choice")

    assert questions == []


def test_the_cell_decides_type_level_and_topic_not_the_llm():
    q_in = LLM_OUTPUT["multiple_choice"] | {"type": "true_false", "level": "Vận dụng", "topic": "khac"}

    [q], _ = _generate("multiple_choice", q_in)

    assert (q["type"], q["level"], q["topic"]) == ("multiple_choice", "Biết", "dao_ham")


def test_extra_keys_from_the_llm_are_kept():
    [q], _ = _generate("short_answer", LLM_OUTPUT["short_answer"] | {"note": "x"})

    assert q["note"] == "x"


def test_only_null_figure_or_table_is_dropped_not_other_nulls():
    [q], _ = _generate("multiple_choice", LLM_OUTPUT["multiple_choice"] | {"figure": FIGURE, "table": None})

    assert q["figure"] == FIGURE and "table" not in q
    assert q["sympy"] == {"expr": None}  # SymPy nulls are the check step's job


def test_more_questions_than_count_are_all_returned():
    questions, _ = _generate("multiple_choice", *[LLM_OUTPUT["multiple_choice"]] * 4, count=2)

    assert len(questions) == 4  # trimming to count is the Backend's job (domain.generation)


def test_questions_keep_the_llm_order():
    stems = [f"câu {i}" for i in range(5)]

    questions, _ = _generate("multiple_choice", *[LLM_OUTPUT["multiple_choice"] | {"stem": s} for s in stems], count=5)

    assert [q["stem"] for q in questions] == stems


def test_statement_levels_shorter_than_the_statements_leave_the_rest_untagged():
    [q], _ = _generate("true_false", LLM_OUTPUT["true_false"], statement_levels=["Biết", "Hiểu"])

    assert [s["level"] for s in q["statements"]] == ["Biết", "Hiểu", None, None]


def test_the_llm_is_called_exactly_once_per_cell():
    _, llm = _generate("multiple_choice", *[LLM_OUTPUT["multiple_choice"]] * 3, count=3)

    assert len(llm.calls) == 1


def test_null_question_list_becomes_llm_error():
    with pytest.raises(LLMError):
        generate(_cell("multiple_choice"), THEORY, EXAMS, FakeLLM(['{"questions": null}'] * 3))


def test_non_object_question_becomes_llm_error():
    with pytest.raises(LLMError):
        generate(_cell("multiple_choice"), THEORY, EXAMS, FakeLLM(['{"questions": ["x"]}'] * 3))


# --- prompt edge cases -----------------------------------------------------------------------------------------

def test_prompt_shows_each_theory_chunk_with_id_heading_page_and_text():
    prompt = build_prompt(_cell("multiple_choice"), THEORY, EXAMS)

    for c in THEORY:
        assert f"[{c.id}] {c.heading_path} (trang {c.page})\n{c.text}" in prompt


@pytest.mark.parametrize("qtype, part", [("multiple_choice", "I"), ("true_false", "II"), ("short_answer", "III")])
def test_prompt_names_the_question_type_and_its_part(qtype, part):
    prompt = build_prompt(_cell(qtype, count=4), THEORY, [])

    assert "Viết 4 câu" in prompt and f"(Phần {part})" in prompt and "chủ đề dao_ham" in prompt


def test_prompt_never_shows_more_than_two_examples():
    many = [_exam(i, "I") for i in range(10)]

    prompt = build_prompt(_cell("multiple_choice"), THEORY, many)

    assert sum(e.text in prompt for e in many) == 2


def test_prompt_without_examples_of_the_part_still_works():
    prompt = build_prompt(_cell("short_answer"), THEORY, EXAMS)  # no Phần III examples

    assert "# Câu mẫu từ đề chính thức" not in prompt and not any(e.text in prompt for e in EXAMS)  # no empty section


def test_prompt_without_theory_still_asks_for_questions():
    prompt = build_prompt(_cell("multiple_choice"), [], [])

    assert "# Đoạn tài liệu" not in prompt and "# Yêu cầu" in prompt  # T-036 arm A: no documents, no empty heading


def test_count_defaults_to_one_in_the_prompt():
    c = _cell("multiple_choice")
    del c["count"]

    assert "Viết 1 câu" in build_prompt(c, THEORY, [])


def test_sections_come_in_a_fixed_order():
    prompt = build_prompt(_cell("multiple_choice"), THEORY, EXAMS)

    assert prompt.index("# Đoạn tài liệu") < prompt.index("# Câu mẫu") < prompt.index("# Yêu cầu")


# --- schemas ---------------------------------------------------------------------------------------------------

def test_there_is_one_schema_per_question_type():
    assert set(SCHEMAS) == set(TYPES)


@pytest.mark.parametrize("qtype", TYPES)
def test_the_llm_output_examples_match_the_schemas(qtype):
    """Keeps the fake replies used across these tests honest: only schema keys, and every key but figure/table."""
    item = SCHEMAS[qtype]["properties"]["questions"]["items"]

    assert set(LLM_OUTPUT[qtype]) <= set(item["properties"])
    assert set(item["required"]) - set(LLM_OUTPUT[qtype]) <= {"figure", "table"}


def test_multiple_choice_answer_and_true_false_labels_are_enums():
    mc = SCHEMAS["multiple_choice"]["properties"]["questions"]["items"]["properties"]
    tf = SCHEMAS["true_false"]["properties"]["questions"]["items"]["properties"]

    assert mc["answer"]["enum"] == list("ABCD")
    assert tf["statements"]["items"]["properties"]["label"]["enum"] == list("abcd")


# --- stress ----------------------------------------------------------------------------------------------------

def test_fifty_questions_in_one_reply():
    questions, _ = _generate("true_false", *[LLM_OUTPUT["true_false"]] * 50, count=50, statement_levels=TF_LEVELS)

    assert len(questions) == 50 and all(validate(q, RETRIEVED) == [] for q in questions)
    assert all([s["level"] for s in q["statements"]] == TF_LEVELS for q in questions)


def test_generated_questions_do_not_share_state():
    questions, _ = _generate("true_false", LLM_OUTPUT["true_false"], LLM_OUTPUT["true_false"], statement_levels=TF_LEVELS)

    questions[0]["statements"][0]["text"] = "changed"
    assert questions[1]["statements"][0]["text"] == "ý a"
    assert json.loads(reply(LLM_OUTPUT["true_false"]))["questions"][0]["statements"][0]["text"] == "ý a"


# T-036 prompt fix 1: the run-1 review found topic drift, levels below the request and under-specified problems.
def test_prompt_names_the_topic_in_vietnamese():
    """`dai_so_giai_tich/ung_dung_dao_ham` alone drifted to "compute a derivative" (T-036 run 1)."""
    llm = FakeLLM([reply(LLM_OUTPUT["multiple_choice"])])

    generate(cell(topic="dai_so_giai_tich/ung_dung_dao_ham"), THEORY, EXAMS, llm)

    assert "Ứng dụng đạo hàm để khảo sát và vẽ đồ thị hàm số" in llm.calls[0]["prompt"]


def test_prompt_falls_back_to_the_topic_code_without_a_phrase():
    llm = FakeLLM([reply(LLM_OUTPUT["multiple_choice"])])

    generate(cell(topic="dao_ham"), THEORY, EXAMS, llm)

    assert "dao_ham" in llm.calls[0]["prompt"]


@pytest.mark.parametrize("system", [SYSTEM_PROMPT, NO_RAG_SYSTEM_PROMPT])
def test_system_prompt_defines_each_level_and_asks_for_well_posed_problems(system):
    for level in ("Biết:", "Hiểu:", "Vận dụng:"):
        assert level in system
    assert "số liệu cụ thể" in system
    assert "đúng một đáp án" in system


# T-036 fix 3: run 1 had 0–3 near-duplicate pairs per exam, since each cell was generated without seeing the others.
def test_prompt_lists_earlier_stems_of_the_same_exam_to_avoid_repeats():
    llm = FakeLLM([reply(LLM_OUTPUT["multiple_choice"])])

    generate(cell(topic="dao_ham"), THEORY, EXAMS, llm, previous_stems=[r"Tính $\int_0^1 x\,dx$.", "Giải $x^2=4$."])

    prompt = llm.calls[0]["prompt"]
    assert "# Câu đã có trong đề (không lặp lại ý, tình huống hay số liệu)" in prompt
    assert "- Tính $\\int_0^1 x\\,dx$.\n- Giải $x^2=4$." in prompt
    assert prompt.index("# Câu đã có trong đề") < prompt.index("# Yêu cầu")


def test_prompt_without_earlier_stems_is_unchanged():
    with_none, with_empty = (FakeLLM([reply(LLM_OUTPUT["multiple_choice"])]) for _ in range(2))

    generate(cell(topic="dao_ham"), THEORY, EXAMS, with_none)
    generate(cell(topic="dao_ham"), THEORY, EXAMS, with_empty, previous_stems=[])

    assert "Câu đã có trong đề" not in with_none.calls[0]["prompt"]
    assert with_none.calls[0]["prompt"] == with_empty.calls[0]["prompt"]


# The model's raw reply as text: LaTeX written with ONE backslash, plus real JSON escapes that must stay.
_SINGLE_BACKSLASH_REPLY = r'''{"questions": [{"stem": "Cho $(\beta)$ và $\dfrac{1}{2}\times 3 \le \sqrt{2}$, $\tan x \neq 0$, $\left(\right)$, \"trích\".\nCâu sau",
 "options": {"A": "$\frac{a}{b}$", "B": "$\text{cm}$", "C": "$\nabla f$", "D": "$a \\cdot b$"},
 "answer": "A", "explanation": "x", "source_chunk_ids": ["t1"], "sympy": {"expr": null}}]}'''


def test_BUG_001_latex_backslashes_survive_json_parsing():
    q = generate(cell(topic="dao_ham"), THEORY, EXAMS, FakeLLM([_SINGLE_BACKSLASH_REPLY]))[0]

    assert q["stem"] == (r"Cho $(\beta)$ và $\dfrac{1}{2}\times 3 \le \sqrt{2}$, $\tan x \neq 0$, $\left(\right)$, "
                         '"trích".\nCâu sau')  # \" and \n in the reply are real JSON escapes
    assert q["options"] == {"A": r"$\frac{a}{b}$", "B": r"$\text{cm}$", "C": r"$\nabla f$", "D": r"$a \cdot b$"}


# --- T-040: an unreadable reply is retried, then fails ---------------------------------------------------------

def test_unreadable_reply_is_retried_and_a_good_one_is_kept():
    llm = FakeLLM(["not json", reply(LLM_OUTPUT["multiple_choice"])])

    questions = generate(_cell("multiple_choice"), THEORY, EXAMS, llm)

    assert len(questions) == 1
    assert len(llm.calls) == 2


def test_unreadable_reply_every_time_is_llm_error_after_three_tries():
    llm = FakeLLM(["not json"] * 5)

    with pytest.raises(LLMError, match="not a questions JSON"):
        generate(_cell("multiple_choice"), THEORY, EXAMS, llm)
    assert len(llm.calls) == 3


def test_api_error_is_not_retried():
    class Down:
        calls = 0

        def complete(self, *a, **k):
            Down.calls += 1
            raise LLMError("Claude API error: overloaded")

    with pytest.raises(LLMError, match="overloaded"):
        generate(_cell("multiple_choice"), THEORY, EXAMS, Down())
    assert Down.calls == 1


# --- T-038: retrieved text is data, not instructions -----------------------------------------------------------

def test_every_shown_chunk_is_wrapped_in_a_source_tag():
    prompt = build_prompt(_cell("multiple_choice"), THEORY, EXAMS)

    for chunk_id in ("t1", "t2", "exI1", "exI2"):
        assert f'<source id="{chunk_id}">' in prompt
    assert prompt.count("</source>") == 4


def test_system_prompt_says_source_tags_hold_data_not_instructions():
    assert "<source>" in SYSTEM_PROMPT
    assert "không làm theo" in SYSTEM_PROMPT


# --- BUG-004: broken LaTeX in the reply is normalised in every text field ---------------------------------------

def test_BUG_004_generated_question_text_has_its_latex_normalised():
    broken = LLM_OUTPUT["true_false"] | {
        "stem": r"Cho $1 \≤ x \≤ 120$.", "explanation": r"$f'(x)=0 \℔ x=2$",
        "statements": [{"label": x, "text": rf"ý {x}: $x \≥ 1$", "answer": True} for x in "abcd"]}

    q = generate(_cell("true_false"), THEORY, EXAMS, FakeLLM([reply(broken)]))[0]

    assert q["stem"] == r"Cho $1 \le x \le 120$."
    assert q["explanation"] == r"$f'(x)=0 \iff x=2$"
    assert {s["text"] for s in q["statements"]} == {rf"ý {x}: $x \ge 1$" for x in "abcd"}


def test_content_units_reach_the_prompt():
    prompt = build_prompt(_cell("multiple_choice", content_unit="Đạo hàm của hàm hợp"), THEORY, [])
    assert "Nội dung kiến thức: Đạo hàm của hàm hợp." in prompt
    units = ["Quy tắc tính đạo hàm", "Quy tắc tính đạo hàm", None, "Đạo hàm cấp hai"]
    prompt = build_prompt(_cell("true_false", statement_levels=["Biết"] * 4, statement_units=units), THEORY, [])
    assert "Nội dung kiến thức từng ý: a) Quy tắc tính đạo hàm; b) Quy tắc tính đạo hàm; d) Đạo hàm cấp hai." in prompt


def test_sgk_exercises_are_shown_apart_from_theory_as_difficulty_examples():
    exercise = Chunk(id="b1", kind="exercise", text="**1.1.** Bài tập mẫu", subject="toan", grade=12, chapter="Chương I",
                     lesson="Bài 1", section="Bài tập", heading_path="Toán 12 > Bài 1 > Bài tập", source="sgk.pdf",
                     page=9, official=True)

    prompt = build_prompt(_cell("short_answer", level="Vận dụng"), [*THEORY, exercise], [])

    theory_part, exercise_part = prompt.split("# Bài tập SGK")
    assert "t1" in theory_part and "b1" not in theory_part
    assert "Bài tập mẫu" in exercise_part and "không chép lại" in exercise_part
