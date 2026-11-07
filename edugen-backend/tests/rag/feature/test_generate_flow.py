"""Tóm tắt: feature test luồng sinh câu cho ô ma trận (F-03, F-04, T-010, T-031): truy xuất → sinh câu (LLM giả) → kiểm tra định dạng + SymPy qua make_generator; câu hợp lệ được giữ, câu lỗi bị loại kèm lý do, lỗi LLM tới Backend dưới dạng LLMError; chạy trên chỉ mục nạp bằng ingest thật (SGK giả + đề chính thức), đủ 10 ô ma trận mẫu và một đề 22 câu. Chỉ LLM và mô hình nhúng là bản giả."""

import copy
import json
import re

import pytest

from app.rag.generation.llm import LLMError
from app.rag.ingest import ingest
from app.rag.pipeline import generate_for_cell, make_generator
from app.rag.storage.lookup import make_chunk_lookup
from app.rag.vocab import PART_BY_TYPE
from tests.rag.fakes import FakeEmbedder, FakeLLM
from tests.rag.support import (
    ALL_EXAMS,
    DAO_HAM,
    LLM_OUTPUT,
    RETRIEVAL,
    XAC_SUAT,
    cell,
    count_words,
    exam_item,
    load,
    memory_client,
    reply,
    sgk_pages_md,
    theory,
    words,
)

DAO_HAM_OLD = "dai_so_giai_tich/dao_ham"  # in the index of the small fixture below


def _small_index():
    """Theory t1, t2 (what LLM_OUTPUT cites) + exam items of each part, as in the pre-refactor pipeline tests."""
    return memory_client([theory(1), theory(2), exam_item(1, DAO_HAM_OLD, "I"), exam_item(2, DAO_HAM_OLD, "I"),
                          exam_item(3, DAO_HAM_OLD, "II")])


def _run(qtype, *questions, **cell_extra):
    llm = FakeLLM([reply(*questions), reply()])  # reply(): the one re-ask after a rejection brings nothing new
    return generate_for_cell(_small_index(), FakeEmbedder(), cell(qtype, topic=DAO_HAM_OLD, **cell_extra), llm), llm


class CitingLLM:
    """Answers like Claude is told to: cites the chunk ids it was shown, `per_call` questions of the asked type."""

    def __init__(self, per_call=None):
        self.per_call, self.calls = per_call, []

    def complete(self, system, prompt, schema):
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        ids = re.findall(r"^\[([0-9a-f]{16}|t\d+)\] ", prompt, re.MULTILINE)
        n = self.per_call or int(re.search(r"Viết (\d+) câu", prompt).group(1))
        qtype = next(t for t in LLM_OUTPUT if schema == _schema(t))
        return reply(*[copy.deepcopy(LLM_OUTPUT[qtype]) | {"stem": f"câu {i}", "source_chunk_ids": ids[:1]}
                       for i in range(n)])


def _schema(qtype):
    from app.rag.generation.generate import SCHEMAS

    return SCHEMAS[qtype]


@pytest.fixture(scope="module")
def full_index(tmp_path_factory):
    """A small SGK book covering every topic of the matrix-cells fixture + the three official exams, via ingest()."""
    topics = sorted({c["topic"] for c in load(RETRIEVAL / "matrix-cells-toan.json")})
    lessons = [(f"Chương {i}", f"Bài {i}", [("1. Lý thuyết", words(200, f"L{i}_"))]) for i in range(1, len(topics) + 1)]
    book = sgk_pages_md(tmp_path_factory.mktemp("sgk") / "sgk-toan-12" / "manual" / "pages.md", lessons)
    client = memory_client()
    ingest([book, *ALL_EXAMS], client, FakeEmbedder(), count_tokens=count_words)
    return client


# --- existing behaviour (pipeline, T-010) ----------------------------------------------------------------------

def test_valid_questions_kept_and_invalid_ones_dropped_with_reasons():
    bad = LLM_OUTPUT["multiple_choice"] | {"source_chunk_ids": ["not-retrieved"]}

    (valid, rejected), llm = _run("multiple_choice", LLM_OUTPUT["multiple_choice"], bad, count=2)

    assert [q["source_chunk_ids"] for q in valid] == [["t1"]]
    assert len(rejected) == 1
    assert rejected[0]["errors"] == ["cites chunk not-retrieved that was not retrieved"]
    assert "t1" in llm.calls[0]["prompt"]  # retrieved theory reached the prompt


def test_make_generator_returns_generate_cell():
    """T-028: the Backend calls generate(cell) without knowing about Qdrant, embeddings or the LLM."""
    llm = FakeLLM([reply(LLM_OUTPUT["multiple_choice"])])

    generate = make_generator(_small_index(), FakeEmbedder(), llm)
    valid, rejected = generate(cell("multiple_choice", topic=DAO_HAM_OLD))

    assert [q["source_chunk_ids"] for q in valid] == [["t1"]]
    assert rejected == []


def test_BUG_005_backend_generator_puts_the_exams_earlier_stems_in_the_prompt():
    """The Backend sends previous_stems in the cell (to_rag_cell); make_generator passes them to the prompt."""
    llm = FakeLLM([reply(LLM_OUTPUT["multiple_choice"])])

    make_generator(_small_index(), FakeEmbedder(), llm)(cell("multiple_choice", topic=DAO_HAM_OLD,
                                                            previous_stems=["ĐỀ BÀI ĐÃ CÓ 1"]))

    assert "- ĐỀ BÀI ĐÃ CÓ 1" in llm.calls[0]["prompt"]


def test_non_json_llm_reply_reaches_backend_as_llm_error():
    """T-028 point 5: generation failures surface only as LLMError."""
    with pytest.raises(LLMError):
        generate_for_cell(_small_index(), FakeEmbedder(), cell(topic=DAO_HAM_OLD), FakeLLM(["not json"] * 3))


# --- SymPy in the flow (T-031, F-04) ---------------------------------------------------------------------------

def test_short_answer_verified_by_sympy_is_kept():
    (valid, rejected), _ = _run("short_answer", LLM_OUTPUT["short_answer"])

    assert rejected == []
    assert valid[0]["sympy"] == {"expr": "diff(x**2, x).subs(x, 1)", "verified": True}


def test_short_answer_sympy_disagrees_is_rejected_with_both_values():
    (valid, rejected), _ = _run("short_answer", LLM_OUTPUT["short_answer"] | {"sympy": {"expr": "1 + 2"}})

    assert valid == []
    assert rejected[0]["errors"] == ["answer 2 but SymPy gives 3 for '1 + 2'"]
    assert rejected[0]["question"]["sympy"]["verified"] is False


def test_validation_and_sympy_errors_are_both_reported():
    bad = LLM_OUTPUT["short_answer"] | {"source_chunk_ids": ["not-retrieved"], "sympy": {"expr": "1 + 2"}}

    (_, rejected), _ = _run("short_answer", bad)

    assert rejected[0]["errors"] == ["cites chunk not-retrieved that was not retrieved",
                                     "answer 2 but SymPy gives 3 for '1 + 2'"]


def test_multiple_choice_null_sympy_expr_is_dropped_in_the_flow():
    (valid, rejected), _ = _run("multiple_choice", LLM_OUTPUT["multiple_choice"])

    assert rejected == [] and "sympy" not in valid[0]


# --- what the Backend can rely on ------------------------------------------------------------------------------

def test_result_unpacks_as_valid_and_rejected():
    result, _ = _run("multiple_choice", LLM_OUTPUT["multiple_choice"])

    assert result.valid == result[0] and result.rejected == result[1] == []


def test_every_valid_question_carries_the_cell_type_level_and_topic():
    (valid, _), _ = _run("true_false", LLM_OUTPUT["true_false"], level="Hiểu")

    assert (valid[0]["type"], valid[0]["level"], valid[0]["topic"]) == ("true_false", "Hiểu", DAO_HAM_OLD)


def test_true_false_statement_levels_reach_the_backend():
    (valid, _), _ = _run("true_false", LLM_OUTPUT["true_false"], statement_levels=["Biết", "Biết", "Hiểu", "Vận dụng"])

    assert [s["level"] for s in valid[0]["statements"]] == ["Biết", "Biết", "Hiểu", "Vận dụng"]


def test_a_cell_can_come_back_short():
    (valid, rejected), _ = _run("multiple_choice", LLM_OUTPUT["multiple_choice"], count=3)

    assert len(valid) == 1 and rejected == []  # never padded; the Backend marks the cell short


def test_extra_questions_are_passed_through_for_the_backend_to_trim():
    distinct = [LLM_OUTPUT["multiple_choice"] | {"stem": f"Câu {i}"} for i in range(5)]  # BUG-005: not repeats
    (valid, _), _ = _run("multiple_choice", *distinct, count=2)

    assert len(valid) == 5


def test_an_empty_reply_gives_nothing_and_no_error():
    assert _run("multiple_choice")[0] == ([], [])


def test_order_is_kept_in_valid_and_in_rejected():
    good = [LLM_OUTPUT["multiple_choice"] | {"stem": f"ok {i}"} for i in range(3)]
    bad = [LLM_OUTPUT["multiple_choice"] | {"stem": f"bad {i}", "answer": "E"} for i in range(3)]

    (valid, rejected), _ = _run("multiple_choice", good[0], bad[0], good[1], bad[1], good[2], bad[2], count=6)

    assert [q["stem"] for q in valid] == ["ok 0", "ok 1", "ok 2"]
    assert [r["question"]["stem"] for r in rejected] == ["bad 0", "bad 1", "bad 2"]


def test_citing_an_exam_item_not_shown_in_the_prompt_is_rejected():
    """Exam items shown in the prompt may be cited (T-036: grade 10–11 cells have no SGK chunks); others may not."""
    (valid, rejected), _ = _run("multiple_choice", LLM_OUTPUT["multiple_choice"] | {"source_chunk_ids": ["e3"]})

    assert valid == [] and rejected[0]["errors"] == ["cites chunk e3 that was not retrieved"]  # e3 is Phần II


def test_an_unknown_topic_fails_before_the_llm_is_called():
    llm = FakeLLM([])

    with pytest.raises(ValueError, match="khong/co"):
        generate_for_cell(_small_index(), FakeEmbedder(), cell(topic="khong/co"), llm)
    assert llm.calls == []


def test_nothing_retrieved_fails_the_cell_without_calling_the_llm():
    llm = FakeLLM([])
    with pytest.raises(LLMError, match="Không tìm thấy nội dung SGK"):
        # chỉ có một câu đề của chủ đề khác: không có lý thuyết, không có câu đề nào để trích
        generate_for_cell(memory_client([exam_item(1, XAC_SUAT)]), FakeEmbedder(), cell(topic=DAO_HAM), llm)
    assert llm.calls == []


def test_an_llm_error_is_not_swallowed():
    class Down:
        def complete(self, *a, **k):
            raise LLMError("Claude API error: overloaded")

    with pytest.raises(LLMError, match="overloaded"):
        make_generator(_small_index(), FakeEmbedder(), Down())(cell(topic=DAO_HAM_OLD))


def test_one_llm_call_per_cell_and_the_generator_is_reusable():
    llm = FakeLLM([reply(LLM_OUTPUT["multiple_choice"])] * 3)
    generate = make_generator(_small_index(), FakeEmbedder(), llm)

    results = [generate(cell(topic=DAO_HAM_OLD)) for _ in range(3)]

    assert len(llm.calls) == 3 and all(len(v) == 1 for v, _ in results)


def test_rejected_questions_keep_the_full_question_for_the_teacher():
    bad = LLM_OUTPUT["multiple_choice"] | {"answer": "E"}

    (_, [r]), _ = _run("multiple_choice", bad)

    assert r["question"]["stem"] == bad["stem"] and r["question"]["type"] == "multiple_choice"


# --- on a real ingested index ----------------------------------------------------------------------------------

@pytest.mark.parametrize("c", load(RETRIEVAL / "matrix-cells-toan.json"), ids=lambda c: f"{c['type']}-{c['topic']}")
def test_every_matrix_fixture_cell_gets_cited_questions_with_resolvable_sources(full_index, c):
    llm = CitingLLM()

    valid, rejected = make_generator(full_index, FakeEmbedder(), llm)(c)

    assert rejected == [] and len(valid) == c["count"]
    found, missing = make_chunk_lookup(full_index)([i for q in valid for i in q["source_chunk_ids"]])
    assert missing == [] and all(f["kind"] == "theory" for f in found.values())


@pytest.mark.parametrize("qtype", ["multiple_choice", "true_false", "short_answer"])
def test_the_prompt_shows_official_examples_of_the_cells_part_only(full_index, qtype):
    llm = CitingLLM()

    make_generator(full_index, FakeEmbedder(), llm)(cell(qtype, topic="dai_so_giai_tich/ung_dung_dao_ham"))

    prompt = llm.calls[0]["prompt"]
    shown_parts = set(re.findall(r"> Phần (I{1,3}) > Câu", prompt))
    assert shown_parts == {PART_BY_TYPE[qtype]}


def test_a_22_question_exam_in_the_official_12_4_6_shape(full_index):
    llm = CitingLLM()
    generate = make_generator(full_index, FakeEmbedder(), llm)
    cells = ([cell("multiple_choice", 3, "dai_so_giai_tich/ung_dung_dao_ham"),
              cell("multiple_choice", 4, "hinh_hoc_do_luong/toa_do_khong_gian"),
              cell("multiple_choice", 5, "thong_ke_xac_suat/xac_suat_co_dieu_kien", level="Hiểu")]
             + [cell("true_false", 1, t, level="Vận dụng", statement_levels=["Biết", "Hiểu", "Hiểu", "Vận dụng"])
                for t in ("dai_so_giai_tich/ung_dung_dao_ham", "dai_so_giai_tich/nguyen_ham_tich_phan",
                          "hinh_hoc_do_luong/toa_do_khong_gian", "thong_ke_xac_suat/xac_suat_co_dieu_kien")]
             + [cell("short_answer", 2, "dai_so_giai_tich/ung_dung_dao_ham", level="Vận dụng"),
                cell("short_answer", 4, "hinh_hoc_do_luong/quan_he_vuong_goc", level="Vận dụng")])

    results = [generate(c) for c in cells]

    by_type = {}
    for c, (valid, rejected) in zip(cells, results):
        assert rejected == [], c
        by_type[c["type"]] = by_type.get(c["type"], 0) + len(valid)
    assert by_type == {"multiple_choice": 12, "true_false": 4, "short_answer": 6}
    assert len(llm.calls) == len(cells)


# --- stress ----------------------------------------------------------------------------------------------------

def test_a_hundred_cells_in_a_row_on_one_generator(full_index):
    llm = CitingLLM(per_call=2)
    generate = make_generator(full_index, FakeEmbedder(), llm)
    topics = ["dai_so_giai_tich/ung_dung_dao_ham", "hinh_hoc_do_luong/toa_do_khong_gian", "thong_ke_xac_suat/xac_suat_co_dien"]
    types = ["multiple_choice", "true_false", "short_answer"]

    total = 0
    for i in range(100):
        valid, rejected = generate(cell(types[i % 3], 2, topics[i % 3]))
        assert rejected == []
        total += len(valid)

    assert total == 200 and len(llm.calls) == 100


def test_a_long_reply_of_mixed_quality_is_split_correctly():
    good = LLM_OUTPUT["short_answer"]
    bad_sympy = good | {"sympy": {"expr": "99"}}
    bad_format = good | {"answer": "12345", "sympy": {"expr": "12345"}}
    questions = [q | {"stem": f"Câu {i}: {q['stem']}"} for i in range(30) for q in (good, bad_sympy, bad_format)]

    (valid, rejected), _ = _run("short_answer", *questions, count=90)

    assert len(valid) == 30 and len(rejected) == 60
    assert json.dumps(valid, ensure_ascii=False)  # what goes back to the Backend is plain JSON


# T-036 spike arms: A = no documents, C = RAG; both get the same fixed format examples.
def _arm_index():
    """Theory t1, t2 + exam items e1, e2 (part I) and e3 (part II) under the cell's topic."""
    return memory_client([theory(1), theory(2), exam_item(1), exam_item(2), exam_item(3, part="II")]), FakeEmbedder()


_ARM_EXAMS = [exam_item(1), exam_item(2), exam_item(3, part="II")]


def test_no_rag_arm_sends_no_documents_and_keeps_free_form_source():
    client, embedder = _arm_index()
    llm = FakeLLM([reply(LLM_OUTPUT["multiple_choice"] | {"source_chunk_ids": ["SGK Toán 12 tập 1, Bài 1"]})])

    valid, rejected = generate_for_cell(client, embedder, cell(), llm, rag=False)

    assert rejected == []
    assert valid[0]["source_chunk_ids"] == ["SGK Toán 12 tập 1, Bài 1"]
    call = llm.calls[0]
    assert "[t1]" not in call["prompt"] and not any(e.text in call["prompt"] for e in _ARM_EXAMS)
    assert "Chỉ dùng kiến thức trong các đoạn tài liệu" not in call["system"]


@pytest.mark.parametrize("rag", [True, False])
def test_format_examples_reach_the_prompt_in_both_arms(rag):
    client, embedder = _arm_index()
    llm = FakeLLM([reply(LLM_OUTPUT["multiple_choice"])])

    generate_for_cell(client, embedder, cell(), llm, rag=rag, format_examples=["VÍ DỤ ĐỊNH DẠNG 1"])

    assert "VÍ DỤ ĐỊNH DẠNG 1" in llm.calls[0]["prompt"]


def test_retrieved_exam_item_can_be_cited():
    """Grade 10–11 cells get no SGK chunks, only exam items, so a question must be able to cite those."""
    llm = FakeLLM([reply(LLM_OUTPUT["multiple_choice"] | {"source_chunk_ids": ["e1"]})])

    _valid, rejected = generate_for_cell(memory_client([exam_item(1)]), FakeEmbedder(), cell(), llm)

    assert rejected == []
    assert "[e1]" in llm.calls[0]["prompt"]


def test_exclude_year_keeps_that_years_exam_items_out_of_the_prompt():
    client, embedder = _arm_index()
    llm = FakeLLM([reply(LLM_OUTPUT["multiple_choice"])] * 2)

    generate_for_cell(client, embedder, cell(), llm)
    generate_for_cell(client, embedder, cell(), llm, exclude_year=2025)

    assert any(e.text in llm.calls[0]["prompt"] for e in _ARM_EXAMS)  # control: without exclusion they do show
    assert not any(e.text in llm.calls[1]["prompt"] for e in _ARM_EXAMS)


@pytest.mark.parametrize("rag", [True, False])
def test_earlier_stems_reach_the_prompt_in_both_arms(rag):
    """T-036 fix 3: the runner passes the stems already generated for this exam."""
    client, embedder = _arm_index()
    llm = FakeLLM([reply(LLM_OUTPUT["multiple_choice"])])

    generate_for_cell(client, embedder, cell(), llm, rag=rag, previous_stems=["ĐỀ BÀI ĐÃ CÓ 1"])

    assert "- ĐỀ BÀI ĐÃ CÓ 1" in llm.calls[0]["prompt"]


# --- guardrails (T-038) ----------------------------------------------------------------------------------------

TOXIC_MC = LLM_OUTPUT["multiple_choice"] | {"stem": "Đồ ngu, đạo hàm của $x^2$ là"}


def test_toxic_question_is_rejected_and_regenerated_once():
    llm = FakeLLM([reply(TOXIC_MC), reply(LLM_OUTPUT["multiple_choice"])])

    valid, rejected = generate_for_cell(_small_index(), FakeEmbedder(), cell(topic=DAO_HAM_OLD), llm)

    assert [q["stem"] for q in valid] == [LLM_OUTPUT["multiple_choice"]["stem"]]
    assert [e for r in rejected for e in r["errors"]] == ["toxic_content: đồ ngu"]
    assert len(llm.calls) == 2
    assert "Viết 1 câu" in llm.calls[1]["prompt"]  # only the missing ones are asked again
    assert "đồ ngu" not in llm.calls[1]["prompt"].lower()  # the reason is sent back, never the offensive words


def test_still_toxic_after_regeneration_stays_rejected():
    llm = FakeLLM([reply(TOXIC_MC), reply(TOXIC_MC)])

    valid, rejected = generate_for_cell(_small_index(), FakeEmbedder(), cell(topic=DAO_HAM_OLD), llm)

    assert valid == [] and len(rejected) == 2
    assert len(llm.calls) == 2  # one regeneration, no loop


# --- every rejection is asked for again once, with the reasons (TC-004 / TC-016 eval: 70% / 50% before) ----------

def test_rejected_question_is_asked_again_once_with_its_errors_and_the_kept_stems():
    good = LLM_OUTPUT["short_answer"] | {"stem": "Câu giữ lại"}
    too_long = LLM_OUTPUT["short_answer"] | {"stem": "Câu dài", "answer": "17450", "sympy": {"expr": "17450 + 0*x"}}
    llm = FakeLLM([reply(good, too_long), reply(LLM_OUTPUT["short_answer"])])

    valid, rejected = generate_for_cell(_small_index(), FakeEmbedder(),
                                        cell("short_answer", count=2, topic=DAO_HAM_OLD), llm)

    assert [q["stem"] for q in valid] == ["Câu giữ lại", LLM_OUTPUT["short_answer"]["stem"]]
    assert [r["question"]["stem"] for r in rejected] == ["Câu dài"]
    again = llm.calls[1]["prompt"]
    assert "Viết 1 câu" in again
    assert "short_answer '17450' does not fit the 4 answer-sheet boxes" in again
    assert "- Câu giữ lại" in again  # the replacement must not repeat what was kept


def test_no_re_ask_when_the_cell_is_already_full():
    extra = LLM_OUTPUT["multiple_choice"] | {"stem": "thừa", "answer": "E"}
    llm = FakeLLM([reply(LLM_OUTPUT["multiple_choice"], extra)])

    valid, rejected = generate_for_cell(_small_index(), FakeEmbedder(), cell(topic=DAO_HAM_OLD), llm)

    assert len(valid) == 1 and len(rejected) == 1
    assert len(llm.calls) == 1


# --- BUG-005: a question repeating one already in the exam (or in the same reply) is rejected ------------------

ASYMPTOTE = r"Tìm tiệm cận đứng của đồ thị hàm số $y=\frac{2x-1}{x+1}$."
HORIZONTAL = r"Cho hàm số $y = \dfrac{3x - 2}{x + 1}$. Tiệm cận ngang của đồ thị hàm số đã cho có phương trình là"


def _with_stems(*stems):
    return [LLM_OUTPUT["multiple_choice"] | {"stem": s} for s in stems]


@pytest.mark.parametrize("again", [
    ASYMPTOTE,
    r"Tìm  tiệm cận đứng của đồ thị hàm số $y = \frac{2x-1}{x+1}$ .",  # spacing and $ … $ only
    r"Hãy tìm tiệm cận đứng của đồ thị hàm số $y=\frac{2x-1}{x+1}$.",  # near-identical wording
])
def test_BUG_005_question_repeating_an_earlier_stem_of_the_exam_is_rejected(again):
    """e81f6617 Q2 / Q11 / Q12: one question, only the options shuffled."""
    llm = FakeLLM([reply(*_with_stems(again)), reply(*_with_stems(again))])

    valid, rejected = generate_for_cell(*_small_index_and_embedder(), cell("multiple_choice", topic=DAO_HAM_OLD),
                                        llm, previous_stems=[ASYMPTOTE])

    assert valid == []
    assert [r["errors"] for r in rejected] == [["repeats a question already in the exam"]] * 2  # asked once more


def test_BUG_005_two_copies_in_one_reply_keep_only_the_first():
    other = r"Tìm tiệm cận ngang của đồ thị hàm số $y=\frac{3x+5}{x-4}$."
    llm = FakeLLM([reply(*_with_stems(ASYMPTOTE, ASYMPTOTE)), reply(*_with_stems(other))])

    valid, rejected = generate_for_cell(*_small_index_and_embedder(),
                                        cell("multiple_choice", count=2, topic=DAO_HAM_OLD), llm)

    assert [q["stem"] for q in valid] == [ASYMPTOTE, other]  # the copy is replaced by a new question
    assert [r["errors"] for r in rejected] == [["repeats a question already in the exam"]]
    assert f"- {ASYMPTOTE}" in llm.calls[1]["prompt"]


@pytest.mark.parametrize("other", [
    r"Tìm tiệm cận ngang của đồ thị hàm số $y=\frac{3x+5}{x-4}$.",  # same topic, another question
    "Tính $f'(2)$.",  # short stems only count as repeats when identical
    # TC-004 eval: same template, another function and asymptote; 90% alike as text, not the same question
    r"Cho hàm số $y = \dfrac{3 - x}{x + 2}$. Tiệm cận đứng của đồ thị hàm số đã cho có phương trình là",
])
def test_BUG_005_different_questions_are_kept(other):
    llm = FakeLLM([reply(*_with_stems(other))])

    valid, rejected = generate_for_cell(*_small_index_and_embedder(), cell("multiple_choice", topic=DAO_HAM_OLD),
                                        llm, previous_stems=[ASYMPTOTE, "Tính $f'(1)$.", HORIZONTAL])

    assert len(valid) == 1 and rejected == []


def _small_index_and_embedder():
    return _small_index(), FakeEmbedder()

