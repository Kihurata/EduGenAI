"""Tóm tắt: unit test truy xuất theo ô ma trận (T-006, T-026) trên Qdrant trong bộ nhớ: lọc đúng môn/bài/chủ đề/phần, tách lý thuyết và câu đề mẫu, chế độ lai và chỉ dense, câu tìm kiếm lấy từ bảng chủ đề, chủ đề lạ báo lỗi; thêm biên (k, dữ liệu rỗng, bài tập không được trả) và áp lực."""

from dataclasses import replace

import pytest

from app.rag.dto import Retrieved
from app.rag.storage.retrieve import TOPIC_QUERIES, retrieve
from app.rag.vocab import OLD_TO_NEW, PART_BY_TYPE, TOPICS
from tests.rag.fakes import FakeEmbedder
from tests.rag.support import DAO_HAM, XAC_SUAT, exam_item, memory_client, theory

MODES = ["hybrid", "dense"]


class RecordingEmbedder(FakeEmbedder):
    def __init__(self):
        self.texts = []

    def embed(self, texts):
        self.texts += texts
        return super().embed(texts)


@pytest.fixture
def client():
    return memory_client(
        [theory(i, "toan", "Bài 1") for i in range(4)]
        + [theory(10 + i, "toan", "Bài 2") for i in range(4)]
        + [theory(20 + i, "ly", "Bài 1") for i in range(4)]
        + [exam_item(i, DAO_HAM, "I") for i in range(3)]
        + [exam_item(10 + i, DAO_HAM, "II") for i in range(3)]
        + [exam_item(20 + i, XAC_SUAT, "I") for i in range(3)]
    )


def _cell(qtype="multiple_choice", topic=DAO_HAM, **extra):
    return {"subject": "toan", "topic": topic, "type": qtype} | extra


# --- existing behaviour ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("mode", MODES)
def test_theory_filtered_by_subject_and_lesson(client, mode):
    theory_chunks, _ = retrieve(client, FakeEmbedder(), _cell(lesson="Bài 1"), mode=mode)

    assert len(theory_chunks) == 4
    assert all(c.kind == "theory" and c.subject == "toan" and c.lesson == "Bài 1" for c in theory_chunks)


@pytest.mark.parametrize("mode", MODES)
def test_cell_returns_theory_and_same_topic_same_part_exam_items_separately(client, mode):
    theory_chunks, exam_items = retrieve(client, FakeEmbedder(), _cell(), mode=mode)

    assert theory_chunks and all(c.kind == "theory" and c.subject == "toan" for c in theory_chunks)
    assert len(exam_items) == 3
    assert all(c.kind == "exam_item" and c.topic == DAO_HAM and c.part == "I" for c in exam_items)


def test_k_limits_theory_results(client):
    theory_chunks, _ = retrieve(client, FakeEmbedder(), _cell("true_false"), k=2)

    assert len(theory_chunks) == 2


@pytest.mark.parametrize("topic", ["dai_so_giai_tich/ung_dung_dao_ham", "dai_so_giai_tich/tiem_can"])
def test_cell_with_new_or_old_topic_code_finds_items_indexed_under_old_code(topic):
    c = memory_client([exam_item(1, "dai_so_giai_tich/tiem_can"), exam_item(2, "dai_so_giai_tich/cap_so_cong")])

    _, exam_items = retrieve(c, FakeEmbedder(), _cell(topic=topic))

    assert [e.id for e in exam_items] == ["e1"]


def test_cell_without_query_searches_with_mapped_vietnamese_phrase(client):
    embedder = RecordingEmbedder()

    retrieve(client, embedder, _cell(topic="dai_so_giai_tich/tiem_can"))

    assert embedder.texts == ["Đường tiệm cận của đồ thị hàm số"]


def test_query_overrides_mapped_phrase(client):
    embedder = RecordingEmbedder()

    retrieve(client, embedder, _cell(query="câu hỏi"))

    assert embedder.texts == ["câu hỏi"]


def test_unknown_topic_raises_naming_the_topic(client):
    with pytest.raises(ValueError, match="dai_so_giai_tich/khong_co"):
        retrieve(client, FakeEmbedder(), _cell(topic="dai_so_giai_tich/khong_co"))


def test_every_new_and_old_topic_code_has_a_phrase():
    # Old codes too: the golden set and matrix-cells fixtures still use them.
    codes = TOPICS | set(OLD_TO_NEW)

    assert {c for c in codes if not TOPIC_QUERIES.get(c, "").strip()} == set()


# --- result shape ----------------------------------------------------------------------------------------------

def test_returns_a_retrieved_dto_of_chunks(client):
    result = retrieve(client, FakeEmbedder(), _cell())

    assert isinstance(result, Retrieved)
    assert result.theory[0].heading_path and result.exam_items[0].question_no is not None


def test_one_query_vector_serves_both_searches(client):
    embedder = RecordingEmbedder()

    retrieve(client, embedder, _cell())

    assert len(embedder.texts) == 1


# --- edge cases ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("qtype", ["multiple_choice", "true_false", "short_answer"])
def test_exam_items_come_from_the_part_of_the_cell_type(qtype):
    c = memory_client([exam_item(i, DAO_HAM, part) for i, part in enumerate(["I", "II", "III"] * 2)])

    _, exam_items = retrieve(c, FakeEmbedder(), _cell(qtype))

    assert exam_items and {e.part for e in exam_items} == {PART_BY_TYPE[qtype]}


@pytest.mark.parametrize("mode", MODES)
def test_k_larger_than_the_data_returns_everything_that_matches(client, mode):
    theory_chunks, exam_items = retrieve(client, FakeEmbedder(), _cell(), k=100, mode=mode)

    assert len(theory_chunks) == 8 and len(exam_items) == 3


@pytest.mark.parametrize("mode", MODES)
def test_k_of_one_returns_one_of_each(client, mode):
    theory_chunks, exam_items = retrieve(client, FakeEmbedder(), _cell(), k=1, mode=mode)

    assert len(theory_chunks) == 1 and len(exam_items) == 1


def test_a_lesson_with_no_chunks_gives_no_theory_but_still_exam_items(client):
    theory_chunks, exam_items = retrieve(client, FakeEmbedder(), _cell(lesson="Bài 99"))

    assert theory_chunks == [] and len(exam_items) == 3


def test_a_subject_with_no_data_gives_nothing(client):
    assert retrieve(client, FakeEmbedder(), _cell() | {"subject": "hoa"}) == ([], [])


def test_a_topic_with_no_exam_items_still_returns_theory(client):
    theory_chunks, exam_items = retrieve(client, FakeEmbedder(), _cell(topic="hinh_hoc_do_luong/toa_do_khong_gian"))

    assert theory_chunks and exam_items == []


def test_exercise_chunks_are_never_retrieved_as_theory():
    c = memory_client([theory(1, kind="exercise"), theory(2)])

    theory_chunks, _ = retrieve(c, FakeEmbedder(), _cell())

    assert [t.id for t in theory_chunks] == ["t2"]


def test_exam_items_of_another_subject_are_not_returned():
    c = memory_client([exam_item(1, DAO_HAM, subject="ly"), exam_item(2, DAO_HAM)])

    _, exam_items = retrieve(c, FakeEmbedder(), _cell())

    assert [e.id for e in exam_items] == ["e2"]


@pytest.mark.parametrize("query", ["", None])
def test_an_empty_query_falls_back_to_the_topic_phrase(client, query):
    embedder = RecordingEmbedder()

    retrieve(client, embedder, _cell(query=query))

    assert embedder.texts == [TOPIC_QUERIES[DAO_HAM]]


def test_a_lesson_of_none_means_any_lesson(client):
    theory_chunks, _ = retrieve(client, FakeEmbedder(), _cell(lesson=None), k=20)

    assert {c.lesson for c in theory_chunks} == {"Bài 1", "Bài 2"}


def test_an_unknown_topic_fails_before_embedding(client):
    embedder = RecordingEmbedder()

    with pytest.raises(ValueError):
        retrieve(client, embedder, _cell(topic="khong/co"))
    assert embedder.texts == []


def test_an_unknown_topic_is_fine_when_the_cell_has_its_own_query(client):
    theory_chunks, exam_items = retrieve(client, FakeEmbedder(), _cell(topic="khong/co", query="đạo hàm"))

    assert theory_chunks and exam_items == []


def test_an_unknown_question_type_raises():
    with pytest.raises(KeyError):
        retrieve(memory_client([theory(1)]), FakeEmbedder(), _cell("essay"))


@pytest.mark.parametrize("topic", sorted(TOPICS))
def test_every_new_topic_retrieves_its_own_and_its_old_coded_items(topic):
    from app.rag.vocab import old_codes

    codes = sorted({topic, *old_codes(topic)})
    c = memory_client([exam_item(i, code) for i, code in enumerate(codes)] + [exam_item(99, "khac/khac")])

    _, exam_items = retrieve(c, FakeEmbedder(), _cell(topic=topic), k=50)

    assert {e.topic for e in exam_items} == set(codes)


# --- stress ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("mode", MODES)
def test_filters_hold_on_a_large_mixed_index(mode):
    chunks = [theory(i, subject=("toan", "ly", "hoa")[i % 3], lesson=f"Bài {i % 7}") for i in range(900)]
    chunks += [exam_item(1000 + i, (DAO_HAM, XAC_SUAT)[i % 2], ("I", "II", "III")[i % 3]) for i in range(300)]
    c = memory_client(chunks)

    theory_chunks, exam_items = retrieve(c, FakeEmbedder(), _cell("true_false", lesson="Bài 3"), k=40, mode=mode)

    assert len(theory_chunks) == 40
    assert all((t.subject, t.lesson, t.kind) == ("toan", "Bài 3", "theory") for t in theory_chunks)
    assert len(exam_items) == 40 and all((e.topic, e.part) == (DAO_HAM, "II") for e in exam_items)


@pytest.mark.parametrize("mode", ["dence", "sparse", "", "HYBRID"])
def test_an_unknown_search_mode_raises_instead_of_silently_running_hybrid(client, mode):
    with pytest.raises(ValueError, match="search mode"):
        retrieve(client, FakeEmbedder(), _cell(), mode=mode)



def test_exclude_year_drops_exam_items_of_that_year():
    """T-036 leakage control: the run on the 2025 matrix must not see the 2025 exam items."""
    c = memory_client([exam_item(1), replace(exam_item(2), year=2026)])

    _, exam_items = retrieve(c, FakeEmbedder(), {"subject": "toan", "topic": DAO_HAM, "type": "multiple_choice"},
                             exclude_year=2025)

    assert [e.id for e in exam_items] == ["e2"]


def test_cell_grade_filters_theory_but_not_exam_items(client):
    """T-036: a grade-11 cell gets no grade-12 SGK chunks; exam items still come back."""
    theory_chunks, exam_items = retrieve(client, FakeEmbedder(), {"subject": "toan", "topic": DAO_HAM,
                                                                  "type": "multiple_choice", "grade": 11})

    assert theory_chunks == []
    assert exam_items


def test_the_search_phrase_is_embedded_as_a_query(client):
    class QueryOnly(FakeEmbedder):
        def embed(self, texts):
            raise AssertionError("documents only")

        def embed_query(self, text):
            self.asked = text
            return super().embed([text])[0]

    embedder = QueryOnly()

    retrieve(client, embedder, _cell(query="đạo hàm"))

    assert embedder.asked == "đạo hàm"


def test_van_dung_cell_also_gets_up_to_2_sgk_exercises_after_the_theory():
    c = memory_client([theory(1), theory(2), *(theory(10 + i, kind="exercise") for i in range(3)),
                       theory(20, subject="ly", kind="exercise")])

    theory_chunks, _ = retrieve(c, FakeEmbedder(), _cell(level="Vận dụng"))

    kinds = [t.kind for t in theory_chunks]
    assert kinds == ["theory", "theory", "exercise", "exercise"]
    assert all(t.subject == "toan" for t in theory_chunks)


@pytest.mark.parametrize("level", ["Biết", "Hiểu"])
def test_lower_level_cells_get_no_exercises(level):
    c = memory_client([theory(1), theory(2, kind="exercise")])

    theory_chunks, _ = retrieve(c, FakeEmbedder(), _cell(level=level))

    assert [t.id for t in theory_chunks] == ["t1"]
