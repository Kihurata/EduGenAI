"""Tóm tắt: unit test bộ cắt đoạn cố định (T-003, dùng làm mốc so sánh trong T-007): cắt theo số token, bỏ qua ranh giới đề mục, không mất và không lặp chữ nào, mỗi đoạn ≤ giới hạn; đoạn mang chương/bài/mục và trang nơi nó bắt đầu để chấm recall theo `lesson` như bộ cắt theo đề mục."""

import random

import pytest

from app.rag.chunking.fixed import chunk_fixed
from app.rag.chunking.theory import chunk_theory
from tests.rag.support import count_words, words


def book(*lessons):
    """lessons: (lesson, [(section, body)]) under one chapter; one page per lesson, numbered from 1."""
    return [(page, f"# Chương I\n\n## {name}\n\n" + "\n\n".join(f"### {t}\n\n{b}" for t, b in sections))
            for page, (name, sections) in enumerate(lessons, start=1)]


def chunk(pages, **kw):
    return chunk_fixed(pages, source="sgk.pdf", count_tokens=count_words, **kw)


def _body_words(chunks):
    return " ".join(c.text for c in chunks).split()


def test_no_pages_gives_no_chunks():
    assert chunk([]) == []


def test_every_chunk_fits_the_token_limit():
    chunks = chunk(book(("Bài 1", [("1. A", words(1000, "a"))])), max_tokens=300)

    assert len(chunks) == 4 and all(count_words(c.text) <= 300 for c in chunks)


def test_no_word_is_lost_or_repeated_and_order_is_kept():
    pages = book(("Bài 1", [("1. A", words(250, "a")), ("2. B", words(250, "b"))]), ("Bài 2", [("1. C", words(250, "c"))]))

    chunks = chunk(pages, max_tokens=100)

    stream = " ".join(md.replace("#", " ") for _, md in pages).split()
    assert _body_words(chunks) == stream


def test_chunks_cut_across_headings():
    chunks = chunk(book(("Bài 1", [("1. A", words(60, "a")), ("2. B", words(60, "b"))])), max_tokens=100)

    assert any("a59" in c.text and "b0" in c.text for c in chunks)  # one window spans both sections


def test_a_chunk_is_labelled_with_where_it_starts():
    pages = book(("Bài 1", [("1. A", words(150, "a"))]), ("Bài 2", [("1. C", words(150, "c"))]))

    chunks = chunk(pages, max_tokens=100)

    last = chunks[-1]
    assert (last.chapter, last.lesson, last.section, last.page) == ("Chương I", "Bài 2", "1. C", 2)
    assert last.heading_path == "Toán 12 > Chương I > Bài 2 > 1. C"
    assert (chunks[0].chapter, chunks[0].section, chunks[0].page) == ("Chương I", "", 1)  # starts on the chapter heading


def test_a_window_counts_for_every_lesson_it_covers():
    """recall@k scores on `expected lesson in chunk.lesson`; a window holding two lessons must count for both,
    or the baseline is penalised for its label, not for its retrieval."""
    chunks = chunk(book(("Bài 1", [("1. A", words(40, "a"))]), ("Bài 2", [("1. C", words(40, "c"))])), max_tokens=500)

    [c] = chunks
    assert c.lesson == "Bài 1 | Bài 2" and "Bài 1" in c.lesson and "Bài 2" in c.lesson


def test_a_window_before_any_lesson_has_no_lesson():
    [c] = chunk([(1, "# Chương I\n\n" + words(20, "x"))])

    assert (c.chapter, c.lesson) == ("Chương I", "")


def test_chunks_are_plain_theory_chunks_of_the_source():
    [c] = chunk(book(("Bài 1", [("Bài tập", words(50))])))

    assert (c.kind, c.subject, c.grade, c.source, c.official) == ("theory", "toan", 12, "sgk.pdf", True)


def test_ids_are_deterministic_unique_and_not_those_of_the_heading_chunker():
    pages = book(("Bài 1", [("1. A", words(400, "a"))]))

    first, second = chunk(pages, max_tokens=100), chunk(pages, max_tokens=100)
    heading = chunk_theory(pages, source="sgk.pdf", count_tokens=count_words)

    assert [c.id for c in first] == [c.id for c in second]
    assert len({c.id for c in first}) == len(first)
    assert not {c.id for c in first} & {c.id for c in heading}


def test_text_before_the_first_heading_is_kept():
    [c] = chunk([(1, words(20, "intro") + "\n\n# Chương I\n\n" + words(20, "x"))])

    assert c.text.startswith("intro0") and c.lesson == ""


@pytest.mark.parametrize("max_tokens", [50, 800])
def test_windows_are_filled_greedily(max_tokens):
    pages = book(("Bài 1", [("1. A", words(2000, "a"))]))

    assert len(chunk(pages, max_tokens=max_tokens)) == -(-count_words(pages[0][1].replace("#", " ")) // max_tokens)


def test_the_default_limit_is_800_tokens():
    assert all(count_words(c.text) <= 800 for c in chunk(book(("Bài 1", [("1. A", words(5000))]))))


def test_other_subject_and_grade_name_the_heading_path():
    [c] = chunk_fixed(book(("Bài 1", [("1. A", words(10))])), source="ly.pdf", subject="ly", grade=11,
                      count_tokens=count_words)

    assert c.heading_path.startswith("Vật lí 11 > ")


@pytest.mark.parametrize("seed", range(10))
def test_random_books_keep_every_word_once_within_the_limit(seed):
    rng = random.Random(seed)
    lessons = [(f"Bài {i}", [(f"{j}. M", words(rng.randint(1, 600), f"L{i}M{j}_")) for j in range(rng.randint(1, 4))])
               for i in range(rng.randint(1, 6))]
    pages = book(*lessons)
    limit = rng.choice([30, 120, 800])

    chunks = chunk(pages, max_tokens=limit)

    assert _body_words(chunks) == " ".join(md.replace("#", " ") for _, md in pages).split()
    assert all(count_words(c.text) <= limit for c in chunks)
