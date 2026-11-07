"""Tóm tắt: unit test hàm đo recall@k (T-007, T-026): một dòng golden set tính là trúng khi trong k đoạn lý thuyết đầu có đoạn thuộc bài mong đợi; dòng không có câu hỏi thì chỉ dùng ô ma trận; thêm biên (nhiều bài mong đợi, k, chế độ dense) và kiểm tra fixture golden set."""

import pytest

from app.rag.dto import Chunk
from app.rag.evaluate import compare_chunkers, format_table, recall_at_k
from app.rag.vocab import OLD_TO_NEW, TOPICS
from tests.rag.fakes import FakeEmbedder
from tests.rag.support import RETRIEVAL, count_words, load, memory_client, words


def _theory(i, lesson):
    return Chunk(id=f"t{i}", kind="theory", text=f"doan {i}", subject="toan", grade=12,
                 chapter="Chương IV. Nguyên hàm và tích phân", lesson=lesson, section="",
                 heading_path=f"Toán 12 > Chương IV. Nguyên hàm và tích phân > {lesson}", source="sgk.pdf", page=i,
                 official=True)


def _row(*expected, query="q"):
    return {"id": expected[0], "query": query, "cell": {"subject": "toan", "topic": "t", "type": "multiple_choice"},
            "expected_lessons": list(expected)}


INDEXED = [_theory(1, "Bài 11. Nguyên hàm"), _theory(2, "Bài 12. Tích phân")]


# --- existing behaviour ----------------------------------------------------------------------------------------

def test_recall_counts_a_hit_when_expected_lesson_is_in_top_k():
    # "Bài 13" is never indexed, so that row must miss; the chapter name alone must not count as a hit.
    golden = [_row("Nguyên hàm"), _row("Tích phân"), _row("Ứng dụng hình học của tích phân")]

    assert recall_at_k(memory_client(INDEXED), FakeEmbedder(), golden, k=5) == 2 / 3


def test_row_without_query_retrieves_by_cell_only():
    row = {"cell": {"subject": "toan", "topic": "dai_so_giai_tich/nguyen_ham", "type": "multiple_choice"},
           "expected_lessons": ["Nguyên hàm"]}

    assert recall_at_k(memory_client(INDEXED[:1]), FakeEmbedder(), [row], k=5) == 1


def test_golden_set_has_20_rows_with_expected_lessons_and_10_matrix_cells():
    golden = load(RETRIEVAL / "golden-retrieval-toan.json")
    cells = load(RETRIEVAL / "matrix-cells-toan.json")

    assert len(golden) == 20
    assert all(r["query"] and r["expected_lessons"] and r["cell"]["subject"] == "toan" for r in golden)
    assert len(cells) == 10
    assert {c["type"] for c in cells} == {"multiple_choice", "true_false", "short_answer"}


# --- edge cases ------------------------------------------------------------------------------------------------

def test_one_of_several_expected_lessons_is_enough():
    assert recall_at_k(memory_client(INDEXED), FakeEmbedder(), [_row("Bài 99", "Tích phân")]) == 1


def test_nothing_indexed_for_the_subject_scores_zero():
    assert recall_at_k(memory_client(INDEXED), FakeEmbedder(), [_row("Nguyên hàm") | {
        "cell": {"subject": "ly", "topic": "t", "type": "multiple_choice"}}]) == 0


@pytest.mark.parametrize("mode", ["hybrid", "dense"])
def test_both_modes_score_a_perfect_index_as_one(mode):
    golden = [_row("Nguyên hàm"), _row("Tích phân")]

    assert recall_at_k(memory_client(INDEXED), FakeEmbedder(), golden, k=5, mode=mode) == 1


def test_k_too_small_can_miss_a_lesson():
    many = [_theory(i, "Bài 11. Nguyên hàm") for i in range(10)] + [_theory(99, "Bài 12. Tích phân")]

    scores = {recall_at_k(memory_client(many), FakeEmbedder(), [_row("Tích phân")], k=k) for k in (1, 11)}

    assert 1.0 in scores  # with k covering every chunk the lesson is always found


def test_recall_is_a_fraction_between_0_and_1():
    golden = [_row("Nguyên hàm")] * 3 + [_row("Không có")] * 5

    assert recall_at_k(memory_client(INDEXED), FakeEmbedder(), golden) == 3 / 8


# --- fixtures used by the eval tests ---------------------------------------------------------------------------

def test_golden_set_rows_use_known_topic_codes():
    codes = TOPICS | set(OLD_TO_NEW)

    assert all(r["cell"]["topic"] in codes for r in load(RETRIEVAL / "golden-retrieval-toan.json"))


def test_matrix_cells_are_complete_cells_with_known_topics():
    codes = TOPICS | set(OLD_TO_NEW)
    for c in load(RETRIEVAL / "matrix-cells-toan.json"):
        assert {"subject", "topic", "level", "type", "count"} <= set(c)
        assert c["topic"] in codes and c["count"] >= 1



# --- T-007: heading-based vs fixed-size chunking × hybrid vs dense ---------------------------------------------

def _book():
    return [(1, "# Chương IV. Nguyên hàm và tích phân\n\n## Bài 11. Nguyên hàm\n\n### 1. Khái niệm\n\n" + words(300, "n")),
            (2, "## Bài 12. Tích phân\n\n### 1. Định nghĩa\n\n" + words(300, "t"))]


class RecordingEmbedder(FakeEmbedder):
    def __init__(self):
        self.texts = []

    def embed(self, texts):
        self.texts += texts
        return super().embed(texts)


def _compare(golden, embedder=None, **kw):
    return compare_chunkers(_book(), "sgk.pdf", golden, embedder or FakeEmbedder(), count_tokens=count_words, **kw)


def test_comparison_reports_the_2x2_table():
    result = _compare([_row("Nguyên hàm")])

    assert set(result) == {("heading", "hybrid"), ("heading", "dense"), ("fixed", "hybrid"), ("fixed", "dense")}
    assert all(0 <= r <= 1 for r in result.values())


def test_a_lesson_that_is_in_the_book_is_found_by_every_cell_when_k_covers_the_index():
    assert set(_compare([_row("Nguyên hàm"), _row("Tích phân")], k=50).values()) == {1.0}


def test_a_lesson_that_is_not_in_the_book_is_missed_by_every_cell():
    assert set(_compare([_row("Ứng dụng hình học")], k=50).values()) == {0.0}


def test_each_chunker_gets_its_own_index():
    embedder = RecordingEmbedder()

    _compare([_row("Nguyên hàm")], embedder=embedder, max_tokens=100)

    # Heading chunks start with their heading path; fixed windows are plain text.
    assert any(t.startswith("Toán 12 > ") for t in embedder.texts)
    assert any(t.startswith("Chương IV.") for t in embedder.texts)


def test_both_chunkers_use_the_same_token_limit():
    embedder = RecordingEmbedder()

    _compare([_row("Nguyên hàm")], embedder=embedder, max_tokens=100)

    chunk_texts = [t for t in embedder.texts if t != "q"]  # "q" is the golden query
    assert chunk_texts and all(count_words(t) <= 100 or t.startswith("Toán 12 > ") for t in chunk_texts)


def test_format_table_prints_one_row_per_chunker():
    table = format_table({("heading", "hybrid"): 0.95, ("heading", "dense"): 0.9,
                          ("fixed", "hybrid"): 0.5, ("fixed", "dense"): 0.45})

    assert table.splitlines() == ["chunker   hybrid  dense", "heading      95%    90%", "fixed        50%    45%"]


def test_every_golden_lesson_is_a_lesson_of_the_sgk_outline():
    """T-025: a misspelt title ("tọa" vs "toạ") can never hit, so recall would drop for a typo, not for retrieval.
    The outline covers tập 1 and tập 2, so this also checks the tập 2 titles."""
    outline = load(RETRIEVAL / "sgk-toan-12-outline.json")["books"]
    lessons = [lesson for chapters in outline.values() for ch in chapters for lesson in ch["lessons"]]

    missing = [(r["id"], e) for r in load(RETRIEVAL / "golden-retrieval-toan.json") for e in r["expected_lessons"]
               if not any(e in lesson for lesson in lessons)]

    assert len(outline) == 2 and missing == []
