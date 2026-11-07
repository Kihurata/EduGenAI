"""BE gọi RAG thật trong cùng process (app.rag), không qua HTTP.

Chỗ nối hai hợp đồng: ô BE (tên chủ đề tiếng Việt) → ô RAG D-008 (mã chủ đề), câu RAG D-008
(khóa tiếng Anh) → câu dạng BE kiểm bằng domain/question.py, và ngược lại khi GV sửa câu.
Không chạy Qdrant/bge-m3/LLM: hàm generate của RAG được thay bằng hàm giả.
"""

import pytest

from app.core.errors import LLMError
from app.domain.cell import Cell
from app.domain.generation import generate_cell
from app.domain.question import parse_question, to_rag
from app.domain.topics import TOPICS
from app.models.enums import CellRunStatus, Level, QuestionType
from app.rag.dto import GenerationResult
from app.rag.generation.llm import LLMError as RagLLMError
from app.rag.storage.retrieve import TOPIC_QUERIES
from app.services import rag_client
from app.services.rag_client import LocalRag, from_rag_question, to_rag_cell

MC, TF, SA = QuestionType.multiple_choice, QuestionType.true_false, QuestionType.short_answer
TOPIC = "Nguyên hàm và tích phân"  # = TOPICS["nguyen_ham_tich_phan"].name


def cell(type_=MC, level=Level.biet, count=2, topic=TOPIC, grade=12, **kw) -> Cell:
    return Cell(id=1, subject="toan", grade=grade, topic=topic, content_unit=None, type=type_,
                level=level, count=count, **kw)  # fmt: skip


def rag_mc(**kw):
    return {
        "type": "multiple_choice", "level": "Biết", "topic": "dai_so_giai_tich/nguyen_ham_tich_phan",
        "stem": "Nguyên hàm của $2x$ là", "options": {"A": "$x^2+C$", "B": "$2$", "C": "$x$", "D": "$2x^2$"},
        "answer": "A", "explanation": "Vì $(x^2)'=2x$.", "source_chunk_ids": ["c1", "c2"],
        "sympy": {"expr": "None", "verified": False},
    } | kw  # fmt: skip


def rag_tf(**kw):
    statements = [
        {"label": label, "text": f"Ý {label}", "answer": answer, "level": "Hiểu"}
        for label, answer in zip("abcd", (True, False, True, True), strict=True)
    ]
    return {
        "type": "true_false", "level": "Hiểu", "topic": "dai_so_giai_tich/nguyen_ham_tich_phan",
        "stem": "Cho hàm số $f(x)=x^2$.", "statements": statements, "explanation": "Lời giải.",
        "source_chunk_ids": ["c3"],
    } | kw  # fmt: skip


def rag_sa(**kw):
    return {
        "type": "short_answer", "level": "Vận dụng", "topic": "dai_so_giai_tich/nguyen_ham_tich_phan",
        "stem": "Tính $\\int_0^1 3x^2\\,dx$.", "answer": "1", "explanation": "Bằng 1.",
        "source_chunk_ids": ["c4"], "sympy": {"expr": "Integral(3*x**2, (x, 0, 1))", "verified": True},
        "figure": "Hình vẽ parabol", "table": [["x", "0", "1"], ["y", "0", "1"]],
    } | kw  # fmt: skip


def fake_rag(valid=(), rejected=(), seen=None):
    def generate(rag_cell):
        if seen is not None:
            seen.append(rag_cell)
        return GenerationResult(list(valid), list(rejected))

    return LocalRag(generate)


# ----- ô BE → ô RAG -----


def test_cell_topic_name_becomes_rag_topic_code():
    rag_cell = to_rag_cell(cell(TF, Level.hieu, 1, statement_levels=(Level.biet, Level.biet, Level.hieu, Level.hieu)))
    assert rag_cell == {
        "subject": "toan", "grade": 12, "topic": "dai_so_giai_tich/nguyen_ham_tich_phan", "type": "true_false",
        "level": "Hiểu", "count": 1, "statement_levels": ["Biết", "Biết", "Hiểu", "Hiểu"],
    }  # fmt: skip


def test_grade_10_cell_resolves_grade_10_topic_and_is_sent_to_rag():
    topic = TOPICS["ham_so_bac_hai"].name
    rag_cell = to_rag_cell(cell(topic=topic, grade=10))
    assert rag_cell["grade"] == 10
    assert rag_cell["topic"] == "dai_so_giai_tich/ham_so_bac_hai"


def test_grade_12_cell_on_a_grade_11_chapter_asks_rag_for_grade_11_theory():
    # lý thuyết không lọc theo chủ đề: gửi lớp của ma trận (12) thì RAG trích SGK 12 không liên quan
    rag_cell = to_rag_cell(cell(topic=TOPICS["mu_logarit"].name, grade=12))
    assert rag_cell["topic"] == "dai_so_giai_tich/mu_logarit"
    assert rag_cell["grade"] == 11


def test_grade_12_topic_does_not_resolve_for_grade_10_cell():
    with pytest.raises(LLMError, match="Toán topic list"):
        to_rag_cell(cell(topic=TOPICS["ung_dung_dao_ham"].name, grade=10))


def test_cell_without_statement_levels_omits_the_key():
    assert "statement_levels" not in to_rag_cell(cell())


def test_unknown_topic_is_an_llm_error_so_only_that_cell_fails():
    run = generate_cell(cell(topic="Chủ đề lạ"), fake_rag())
    assert run.status is CellRunStatus.error
    assert "Chủ đề lạ" in run.error


@pytest.mark.parametrize("code", sorted(TOPICS))
def test_every_backend_topic_has_a_rag_search_phrase(code):
    assert TOPIC_QUERIES.get(f"{TOPICS[code].strand}/{code}")


# ----- câu RAG → câu BE -----


@pytest.mark.parametrize(("type_", "level", "question"), [(MC, Level.biet, rag_mc()), (TF, Level.hieu, rag_tf()), (SA, Level.van_dung, rag_sa())])
def test_rag_questions_pass_backend_structure_check(type_, level, question):
    normalized, errors = parse_question(from_rag_question(question), cell(type_, level))
    assert errors == []
    assert normalized["citations"] == question["source_chunk_ids"]


def test_multiple_choice_options_are_kept_in_a_to_d_order():
    shuffled = rag_mc(options={"D": "d", "B": "b", "A": "a", "C": "c"})
    normalized, _ = parse_question(from_rag_question(shuffled), cell())
    assert normalized["options"] == ["a", "b", "c", "d"]
    assert normalized["answer"] == "A"


def test_true_false_answers_become_dap_an_string():
    normalized, _ = parse_question(from_rag_question(rag_tf()), cell(TF, Level.hieu))
    assert normalized["answer"] == "ĐSĐĐ"
    assert [s["correct"] for s in normalized["statements"]] == [True, False, True, True]


def test_sympy_figure_and_table_are_kept():
    normalized, _ = parse_question(from_rag_question(rag_sa()), cell(SA, Level.van_dung))
    assert normalized["check"] == {"expr": "Integral(3*x**2, (x, 0, 1))", "verified": True}
    assert normalized["figure"] == "Hình vẽ parabol"
    assert normalized["table"] == [["x", "0", "1"], ["y", "0", "1"]]


def test_malformed_rag_question_is_rejected_not_crashing():
    broken = rag_mc(options="không phải dict", answer=None)
    normalized, errors = parse_question(from_rag_question(broken), cell())
    assert normalized is None and errors


def test_generate_sends_rag_cell_and_returns_valid_and_rejected():
    seen = []
    rejected = [{"question": rag_mc(answer="E"), "errors": ["multiple_choice answer 'E' is not A–D"]}]
    run = generate_cell(cell(count=2), fake_rag([rag_mc(), rag_mc()], rejected, seen))
    assert seen[0]["topic"] == "dai_so_giai_tich/nguyen_ham_tich_phan"
    assert run.status is CellRunStatus.complete
    assert len(run.questions) == 2 and run.rejected_count == 1


def test_rag_llm_error_marks_the_cell_as_error():
    def boom(_):
        raise RagLLMError("Gemini quota")

    run = generate_cell(cell(), LocalRag(boom))
    assert run.status is CellRunStatus.error
    assert "Gemini quota" in run.error


def test_no_sgk_found_error_keeps_topic_and_reason_in_the_cell_error():
    def no_theory(_):
        raise RagLLMError("Không tìm thấy nội dung SGK cho chủ đề dai_so_giai_tich/nguyen_ham_tich_phan (môn toan)")

    run = generate_cell(cell(), LocalRag(no_theory))
    assert run.status is CellRunStatus.error
    assert "Không tìm thấy nội dung SGK" in run.error and "dai_so_giai_tich/nguyen_ham_tich_phan" in run.error


# ----- GV sửa câu → RAG kiểm -----


def test_teacher_edit_is_checked_by_rag_validator():
    normalized, _ = parse_question(from_rag_question(rag_mc()), cell())
    assert fake_rag().validate(to_rag(normalized), cell()) == []


def test_teacher_edit_without_citations_is_rejected_by_rag():
    normalized, _ = parse_question(from_rag_question(rag_mc()), cell())
    errors = fake_rag().validate(to_rag(normalized | {"citations": []}), cell())
    assert errors == ["no source_chunk_ids"]


def test_teacher_edit_of_short_answer_does_not_need_a_sympy_expression():
    normalized, _ = parse_question(from_rag_question(rag_sa()), cell(SA, Level.van_dung))
    assert fake_rag().validate(to_rag(normalized | {"check": None}), cell(SA, Level.van_dung)) == []


# ----- nạp file và dựng RAG thật -----


def test_real_rag_is_built_once_per_process(monkeypatch):
    built = []
    monkeypatch.setattr(rag_client.settings, "rag_mock_samples", None)
    monkeypatch.setattr(rag_client, "_build_rag", lambda: built.append(1) or ((lambda c: GenerationResult([], [])), (lambda chunks: None), (lambda school_id, source=None: None)))
    rag_client.local_rag.cache_clear()
    try:
        assert rag_client.get_rag_client() is rag_client.get_rag_client()
        assert isinstance(rag_client.get_rag_client(), LocalRag)
        assert built == [1]
    finally:
        rag_client.local_rag.cache_clear()


def test_rag_that_cannot_start_fails_each_cell_with_the_reason(monkeypatch):
    def no_index():
        raise RuntimeError("Qdrant chưa có collection chunks")

    monkeypatch.setattr(rag_client, "_build_rag", no_index)
    rag_client.local_rag.cache_clear()
    try:
        run = generate_cell(cell(), rag_client.local_rag())
    finally:
        rag_client.local_rag.cache_clear()
    assert run.status is CellRunStatus.error
    assert "Qdrant chưa có collection chunks" in run.error


# ----- RBAC: trường của ô đi tới truy xuất -----


def test_cell_school_is_sent_to_rag():
    assert to_rag_cell(cell(school_id="s1"))["school_id"] == "s1"


def test_cell_without_school_omits_the_key():
    assert "school_id" not in to_rag_cell(cell())


def test_cell_teacher_is_sent_to_rag():
    assert to_rag_cell(cell(school_id="s1", teacher_id="u1"))["teacher_id"] == "u1"
    assert "teacher_id" not in to_rag_cell(cell(school_id="s1"))


def test_db_cell_takes_the_teacher_from_the_matrix_owner():
    from types import SimpleNamespace

    from app.services.exam_jobs import cell_of

    matrix = SimpleNamespace(subject=SimpleNamespace(code="toan"), grade=12, name=None, school_id="s-1", owner_id="u-1")
    row = SimpleNamespace(sort_order=1, topic=TOPIC, content_unit=None, question_type=MC, level=Level.biet,
                          question_count=2, statement_levels=None, statement_units=None, competency_codes=None)

    assert cell_of(matrix, row).teacher_id == "u-1"


# ----- D-017: loại đề của ma trận → ô RAG -----


@pytest.mark.parametrize("kind", ["tot_nghiep", "dinh_ky_7991"])
def test_matrix_exam_kind_is_sent_to_rag(kind):
    assert to_rag_cell(cell(exam_kind=kind))["exam_kind"] == kind


def test_cell_without_exam_kind_omits_the_key():
    assert "exam_kind" not in to_rag_cell(cell())


@pytest.mark.parametrize(("name", "kind"), [("KTGK HK1 Toán 10", "dinh_ky_7991"), ("Đề cuối kỳ 2", "dinh_ky_7991"),
                                            ("Đề thi tốt nghiệp THPT 2025", "tot_nghiep"), (None, "tot_nghiep")])
def test_db_cell_takes_exam_kind_from_the_matrix_name(name, kind):
    from types import SimpleNamespace

    from app.services.exam_jobs import cell_of

    matrix = SimpleNamespace(subject=SimpleNamespace(code="toan"), grade=10, name=name, school_id="s-1", owner_id="u-1")
    row = SimpleNamespace(sort_order=1, topic=TOPIC, content_unit=None, question_type=MC, level=Level.biet,
                          question_count=2, statement_levels=None, statement_units=None, competency_codes=None)

    assert cell_of(matrix, row).exam_kind == kind


# ----- BUG-005: earlier stems of the exam reach the RAG prompt -----


def test_earlier_stems_are_sent_to_rag():
    assert to_rag_cell(cell(previous_stems=("Câu A", "Câu B")))["previous_stems"] == ["Câu A", "Câu B"]


def test_cell_without_earlier_stems_omits_the_key():
    assert "previous_stems" not in to_rag_cell(cell())



def test_content_units_reach_the_rag_cell():
    units = ("Tích phân", "Tích phân", "Nguyên hàm", None)
    rag_cell = to_rag_cell(cell(TF, Level.hieu, 1, statement_levels=(Level.biet,) * 4, statement_units=units))
    assert rag_cell["statement_units"] == list(units)
    with_unit = Cell(id=1, subject="toan", grade=12, topic=TOPIC, content_unit="Tích phân", type=MC,
                     level=Level.biet, count=1)  # fmt: skip
    assert to_rag_cell(with_unit)["content_unit"] == "Tích phân"
    assert "content_unit" not in to_rag_cell(cell()) and "statement_units" not in to_rag_cell(cell())
