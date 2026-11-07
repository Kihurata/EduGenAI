"""Bản giả lập RAG từ ket_qua_mau.json: thay RAG thật trong test và khi chạy thử.

Đầu ra mong muốn:
- Trả đủ `count` câu `cau_hoi` đúng dạng của ô, mức độ ghi theo ô.
- Không có mẫu cho dạng câu → trả rỗng (ô thành short), không ném lỗi.
- Câu giả lập đi qua generate_cell là hợp lệ và ô complete.
"""

from pathlib import Path

from app.domain.cell import Cell
from app.domain.generation import generate_cell
from app.models.enums import CellRunStatus, Level, QuestionType
from app.services.rag_mock import SampleRag

SAMPLES = Path(__file__).parents[1] / "fixtures" / "rag" / "ket_qua_mau.json"
MC, TF, SA = QuestionType.multiple_choice, QuestionType.true_false, QuestionType.short_answer
B, H, VD = Level.biet, Level.hieu, Level.van_dung


def cell(type_: QuestionType, level: Level, count: int) -> Cell:
    statements = (B, B, H, H) if type_ is TF else None
    return Cell(3, "toan", 10, "Vectơ", None, type_, level, count, statements)


def test_returns_count_questions_of_the_cell_type_and_level():
    rag = SampleRag.from_file(SAMPLES)
    valid, rejected = rag.generate(cell(MC, H, 4))
    assert rejected == []
    assert len(valid) == 4
    assert {q["dang"] for q in valid} == {"nhieu_lua_chon"}
    assert {q["muc_do"] for q in valid} == {"Hieu"}


def test_returned_questions_are_copies():
    rag = SampleRag.from_file(SAMPLES)
    valid, _ = rag.generate(cell(SA, VD, 2))
    valid[0]["de_bai"] = "đã sửa"
    assert rag.generate(cell(SA, VD, 1))[0][0]["de_bai"] != "đã sửa"


def test_type_without_samples_returns_nothing():
    rag = SampleRag([{"cau_hoi": {"dang": "nhieu_lua_chon", "muc_do": "Biet"}}])
    assert rag.generate(cell(TF, H, 1)) == ([], [])


def test_every_type_goes_through_generation_complete():
    rag = SampleRag.from_file(SAMPLES)
    for c in [cell(MC, B, 3), cell(TF, H, 2), cell(SA, VD, 2)]:
        run = generate_cell(c, rag)
        assert run.status == CellRunStatus.complete, run
        assert run.rejected_count == 0
        assert {q["type"] for q in run.questions} == {c.type.value}


def test_validate_uses_be_structure_check():
    rag = SampleRag.from_file(SAMPLES)
    assert rag.validate({"dang": "nhieu_lua_chon"}, None) != []


def test_sample_rag_ingest_is_immediately_done():
    rag = SampleRag.from_file(SAMPLES)
    assert rag.ingest_status(rag.ingest(b"x", "a.pdf", {})) == ("done", None)


# ----- mẫu hình khối để thử cả luồng vẽ hình với FE, không cần LLM -----

FIGURES = Path(__file__).parents[1] / "fixtures" / "rag" / "ket_qua_mau_hinh.json"


def test_from_files_keeps_every_question_in_file_order():
    both = SampleRag.from_files(SAMPLES, FIGURES)
    assert both.questions[: len(SampleRag.from_file(SAMPLES).questions)] == SampleRag.from_file(SAMPLES).questions
    assert len(both.questions) == len(SampleRag.from_file(SAMPLES).questions) + len(SampleRag.from_file(FIGURES).questions)


SOLID_OF_LEVEL = {B: "box", H: "pyramid", VD: "prism"}  # mỗi mức một hình, để ô nào cũng có hình khác nhau


def test_each_level_has_one_figure_sample_with_its_own_solid():
    rag = SampleRag.from_file(FIGURES)
    for level, solid in SOLID_OF_LEVEL.items():
        valid, rejected = rag.generate(cell(MC, level, 1))
        assert rejected == []
        assert valid[0]["hinh_ve"]["solid"] == solid
        assert rag.validate(valid[0], cell(MC, level, 1)) == []


def test_figure_samples_get_an_svg_through_generate_cell():
    for level in SOLID_OF_LEVEL:
        run = generate_cell(cell(MC, level, 1), SampleRag.from_file(FIGURES))
        assert run.status is CellRunStatus.complete
        assert run.questions[0]["figure_svg"].startswith("<svg")
        assert run.questions[0]["figure"]  # mô tả chữ luôn đi kèm để dự phòng


def test_with_the_figure_file_first_every_mc_cell_starts_with_a_figure():
    rag = SampleRag.from_files(FIGURES, SAMPLES)
    for level, solid in SOLID_OF_LEVEL.items():
        first, *rest = rag.generate(cell(MC, level, 2))[0]
        assert first["hinh_ve"]["solid"] == solid and "hinh_ve" not in rest[0]


def test_figure_sample_stems_use_the_fixed_vertex_names_of_the_drawing():
    stems = {q["hinh_ve"]["solid"]: q["de_bai"] for q in SampleRag.from_file(FIGURES).questions}
    assert "ABCD.A'B'C'D'" in stems["box"] and "S.ABCD" in stems["pyramid"] and "ABC.A'B'C'" in stems["prism"]


def test_cycling_through_both_files_still_returns_exactly_count_questions():
    valid, _ = SampleRag.from_files(SAMPLES, FIGURES).generate(cell(MC, B, 9))
    assert len(valid) == 9 and sum("hinh_ve" in q for q in valid) >= 3
