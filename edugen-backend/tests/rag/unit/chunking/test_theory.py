"""Tóm tắt: unit test bộ cắt đoạn lý thuyết SGK (T-003, D-003) với bộ đếm token giả (đếm từ): theo đề mục, không cắt công thức $$, mục dài cắt ≤ 800 token, mục ngắn gộp, Bài tập là exercise, Ví dụ không tách lời giải; thêm trường hợp biên và test áp lực ngẫu nhiên giữ các bất biến."""

import random

import pytest

from app.rag.chunking.theory import chunk_theory, read_pages_md
from tests.rag.support import count_words, words


def lesson(*sections, chapter="Chương I. Ứng dụng đạo hàm", name="Bài 1. Tính đơn điệu", page=5):
    """sections: (title, body) -> one page of Markdown under one chapter > lesson."""
    md = f"# {chapter}\n\n## {name}\n\n" + "\n\n".join(f"### {title}\n\n{body}" for title, body in sections)
    return [(page, md)]


def chunk(pages, **kw):
    return chunk_theory(pages, source="sgk.pdf", count_tokens=count_words, **kw)


# --- existing behaviour (T-003) --------------------------------------------------------------------------------

def test_lesson_with_3_muc_gives_3_chunks_each_starting_with_heading_path():
    pages = lesson(("1. Mục một", words(150, "a")), ("2. Mục hai", words(150, "b")), ("3. Mục ba", words(150, "c")))

    chunks = chunk(pages)

    assert len(chunks) == 3
    for c, title in zip(chunks, ["1. Mục một", "2. Mục hai", "3. Mục ba"]):
        assert c.heading_path == f"Toán 12 > Chương I. Ứng dụng đạo hàm > Bài 1. Tính đơn điệu > {title}"
        assert c.text.startswith(c.heading_path)
        assert (c.kind, c.subject, c.grade, c.page, c.source) == ("theory", "toan", 12, 5, "sgk.pdf")
        assert (c.chapter, c.lesson, c.section) == ("Chương I. Ứng dụng đạo hàm", "Bài 1. Tính đơn điệu", title)


def test_display_formula_on_size_boundary_stays_whole():
    formula = "$$\n\\begin{cases} " + words(60, "f") + " \\\\\n\n" + words(40, "g") + " \\end{cases}\n$$"
    body = "\n\n".join([words(350, "p"), words(350, "q"), formula, words(200, "r")])

    chunks = chunk(lesson(("1. Mục", body)))

    assert len(chunks) > 1
    assert sum(formula in c.text for c in chunks) == 1
    assert all(c.text.count("$$") % 2 == 0 for c in chunks)


def test_2000_token_section_split_at_paragraph_breaks_and_pieces_le_800():
    paragraphs = [words(100, f"p{i}_") for i in range(20)]

    chunks = chunk(lesson(("1. Mục dài", "\n\n".join(paragraphs))))

    assert len(chunks) >= 3
    assert all(count_words(c.text) <= 800 for c in chunks)
    assert all(sum(p in c.text for c in chunks) == 1 for p in paragraphs)  # no paragraph cut or repeated
    assert all(c.text.startswith(c.heading_path) for c in chunks)


def test_40_token_section_is_merged_with_its_neighbour():
    chunks = chunk(lesson(("1. Mục một", words(300, "a")), ("2. Mục ngắn", words(40, "b"))))

    assert len(chunks) == 1
    assert words(40, "b") in chunks[0].text and "2. Mục ngắn" in chunks[0].text


def test_short_bai_tap_section_is_an_exercise_chunk_not_merged_into_theory():
    exercise = "**1.1.** " + words(40, "e")

    chunks = chunk(lesson(("1. Mục một", words(300, "a")), ("Bài tập", exercise)))

    assert [(c.section, c.kind) for c in chunks] == [("1. Mục một", "theory"), ("Bài tập", "exercise")]
    assert exercise in chunks[1].text and words(300, "a") not in chunks[1].text
    assert "**1.1.**" not in chunks[0].text


def test_short_theory_section_is_not_merged_into_an_exercise_chunk():
    chunks = chunk(lesson(("Bài tập", "**1.1.** " + words(150, "e")), ("2. Mục ngắn", words(40, "b"))))

    exercise, = [c for c in chunks if c.kind == "exercise"]
    assert words(40, "b") not in exercise.text
    assert any(words(40, "b") in c.text and c.kind == "theory" for c in chunks)


def test_vi_du_and_its_giai_on_size_boundary_stay_in_one_chunk():
    vi_du, giai = "**Ví dụ 1.** " + words(60, "v"), "*Giải.* " + words(100, "s")
    body = "\n\n".join([words(350, "p"), words(300, "q"), vi_du, giai, words(100, "r")])

    chunks = chunk(lesson(("1. Mục", body)))

    assert sum(vi_du in c.text and giai in c.text for c in chunks) == 1
    assert not any(c.text.split("\n\n")[1].startswith("*Giải.*") for c in chunks)


def test_page_comes_from_where_the_section_starts():
    pages = [(5, "# Chương I. X\n\n## Bài 1. Y\n\n### 1. A\n\n" + words(150, "a")),
             (6, words(50, "a2") + "\n\n### 2. B\n\n" + words(150, "b"))]

    chunks = chunk(pages)

    assert [(c.section, c.page) for c in chunks] == [("1. A", 5), ("2. B", 6)]
    assert words(50, "a2") in chunks[0].text


def test_ids_are_deterministic_and_unique():
    pages = lesson(("1. A", words(150, "a")), ("2. B", words(150, "b")))
    first, second = chunk(pages), chunk(pages)
    assert [c.id for c in first] == [c.id for c in second]
    assert len({c.id for c in first}) == len(first)


def test_read_pages_md_splits_marker_page_separators(tmp_path):
    md = tmp_path / "pages.md"
    md.write_text("{5}" + "-" * 48 + "\n\n# Chương I\n\nabc\n\n{6}" + "-" * 48 + "\n\ndef\n", encoding="utf-8")

    assert read_pages_md(md) == [(5, "# Chương I\n\nabc"), (6, "def")]


# --- edge cases ------------------------------------------------------------------------------------------------

def test_no_pages_gives_no_chunks():
    assert chunk([]) == []


def test_headings_without_paragraphs_give_no_chunks():
    assert chunk([(1, "# Chương I\n\n## Bài 1\n\n### 1. Mục\n\n### 2. Mục")]) == []


def test_text_before_the_first_heading_is_dropped():
    pages = [(1, words(30, "intro") + "\n\n# Chương I\n\n## Bài 1\n\n### 1. A\n\n" + words(150, "a"))]

    [c] = chunk(pages)

    assert "intro0" not in c.text


def test_a_single_paragraph_over_the_limit_stays_whole():
    huge = words(1200, "h")

    chunks = chunk(lesson(("1. Mục", huge)))

    assert len(chunks) == 1 and huge in chunks[0].text  # a formula or table is never cut


@pytest.mark.parametrize("title", ["Bài tập", "BÀI TẬP", "Bài tập cuối chương I", "Bài   tập"])
def test_every_spelling_of_bai_tap_is_an_exercise(title):
    [c] = chunk(lesson((title, words(150, "e"))))

    assert c.kind == "exercise"


def test_bai_tap_inside_a_title_does_not_make_theory_an_exercise():
    [c] = chunk(lesson(("1. Ôn lại bài tập", words(150, "a"))))

    assert c.kind == "theory"  # the rule matches titles that start with "Bài tập"


def test_a_new_chapter_resets_lesson_and_section_titles():
    pages = [(1, "# Chương I\n\n## Bài 1\n\n### 1. A\n\n" + words(150, "a")
              + "\n\n# Chương II\n\n" + words(150, "b"))]

    chunks = chunk(pages)

    assert [(c.chapter, c.lesson, c.section) for c in chunks] == [("Chương I", "Bài 1", "1. A"), ("Chương II", "", "")]
    assert chunks[1].heading_path == "Toán 12 > Chương II"


def test_a_new_lesson_resets_the_section_title():
    pages = [(1, "# Chương I\n\n## Bài 1\n\n### 1. A\n\n" + words(150, "a") + "\n\n## Bài 2\n\n" + words(150, "b"))]

    chunks = chunk(pages)

    assert [(c.lesson, c.section) for c in chunks] == [("Bài 1", "1. A"), ("Bài 2", "")]


def test_a_small_first_section_merges_forward_into_the_next_section_of_the_same_chapter():
    chunks = chunk(lesson(("1. Ngắn", words(30, "s")), ("2. Dài", words(300, "l"))))

    [c] = chunks
    assert c.text.index(words(30, "s")) < c.text.index(words(300, "l"))
    assert "### 2. Dài" not in c.text and "### 1. Ngắn" in c.text
    assert c.section == "2. Dài"


def test_small_sections_never_merge_across_chapters():
    pages = [(1, "# Chương I\n\n## Bài 1\n\n### 1. A\n\n" + words(40, "a")),
             (2, "# Chương II\n\n## Bài 2\n\n### 1. B\n\n" + words(40, "b"))]

    chunks = chunk(pages)

    assert [c.chapter for c in chunks] == ["Chương I", "Chương II"]


def test_a_small_section_stays_alone_when_merging_would_break_the_limit():
    chunks = chunk(lesson(("1. Gần đầy", words(780, "a")), ("2. Ngắn", words(40, "b"))))

    assert len(chunks) == 2
    assert all(count_words(c.text) <= 800 for c in chunks)


def test_custom_limits_are_respected():
    paragraphs = [words(30, f"p{i}_") for i in range(10)]

    chunks = chunk(lesson(("1. Mục", "\n\n".join(paragraphs))), max_tokens=100, min_tokens=10)

    assert len(chunks) > 3 and all(count_words(c.text) <= 100 for c in chunks)


def test_other_subject_and_grade_name_the_heading_path():
    [c] = chunk_theory(lesson(("1. Động lượng", words(150))), source="sgk-ly.pdf", subject="ly", grade=11,
                       count_tokens=count_words)

    assert c.heading_path.startswith("Vật lí 11 > ") and (c.subject, c.grade) == ("ly", 11)


def test_same_text_from_another_source_gets_another_id():
    pages = lesson(("1. A", words(150)))

    a = chunk_theory(pages, source="tap-1.pdf", count_tokens=count_words)
    b = chunk_theory(pages, source="tap-2.pdf", count_tokens=count_words)

    assert a[0].id != b[0].id


def test_ids_are_16_hex_characters():
    [c] = chunk(lesson(("1. A", words(150))))

    assert len(c.id) == 16 and int(c.id, 16) >= 0


def test_an_unclosed_formula_only_affects_its_own_page():
    pages = [(1, "# Chương I\n\n## Bài 1\n\n### 1. A\n\n$$ x = " + words(150, "a")),
             (2, "### 2. B\n\n" + words(150, "b"))]

    chunks = chunk(pages)

    assert [c.section for c in chunks] == ["1. A", "2. B"]


def test_labelled_block_runs_until_the_next_label():
    vi_du_1 = "**Ví dụ 1.** " + words(30, "v1")
    vi_du_2 = "**Ví dụ 2.** " + words(30, "v2")
    body = "\n\n".join([words(120, "p"), vi_du_1, words(10, "g1"), vi_du_2, words(10, "g2")])

    [c] = chunk(lesson(("1. Mục", body)))

    paras = c.text.split("\n\n")
    assert any(p.startswith("**Ví dụ 1.**") for p in paras) and any(p.startswith("**Ví dụ 2.**") for p in paras)


def test_vietnamese_text_is_kept_exactly():
    body = "Hàm số $y=f(x)$ đồng biến trên khoảng $(a;b)$ nếu " + words(120)

    [c] = chunk(lesson(("1. Định nghĩa", body)))

    assert body in c.text


@pytest.mark.parametrize("dashes", [9, 5])
def test_short_dash_runs_are_not_page_separators(tmp_path, dashes):
    md = tmp_path / "pages.md"
    md.write_text("{1}" + "-" * 48 + "\n\nabc\n\n{2}" + "-" * dashes + "\n\ndef\n", encoding="utf-8")

    assert [p for p, _ in read_pages_md(md)] == [1]


def test_read_pages_md_without_separators_gives_no_pages(tmp_path):
    md = tmp_path / "pages.md"
    md.write_text("# Chương I\n\nabc\n", encoding="utf-8")

    assert read_pages_md(md) == []


def test_read_pages_md_keeps_non_sequential_page_numbers(tmp_path):
    md = tmp_path / "pages.md"
    md.write_text("".join("{" + str(n) + "}" + "-" * 20 + f"\n\np{n}\n\n" for n in (10, 3, 250)), encoding="utf-8")

    assert read_pages_md(md) == [(10, "p10"), (3, "p3"), (250, "p250")]


# --- stress: random books, invariants hold ---------------------------------------------------------------------

def _random_book(rng, n_lessons=6):
    pages, paragraphs = [], []
    for li in range(n_lessons):
        md = [f"# Chương {li // 3 + 1}", f"## Bài {li + 1}"]
        for si in range(rng.randint(1, 5)):
            title = "Bài tập" if rng.random() < 0.2 else f"{si + 1}. Mục {si + 1}"
            md.append(f"### {title}")
            for pi in range(rng.randint(1, 6)):
                p = words(rng.choice([5, 40, 120, 300, 900]), f"L{li}S{si}P{pi}_")
                if rng.random() < 0.15:
                    p = "$$\n" + p + "\n$$"
                paragraphs.append(p)
                md.append(p)
        pages.append((li + 1, "\n\n".join(md)))
    return pages, paragraphs


@pytest.mark.parametrize("seed", range(25))
def test_random_books_keep_every_paragraph_once_and_respect_the_limit(seed):
    pages, paragraphs = _random_book(random.Random(seed))

    chunks = chunk(pages)

    joined = "\n\n".join(c.text for c in chunks)
    assert all(joined.count(p) == 1 for p in paragraphs)  # nothing lost, nothing repeated
    assert len({c.id for c in chunks}) == len(chunks)
    for c in chunks:
        assert c.text.startswith(c.heading_path)
        assert c.text.count("$$") % 2 == 0
        too_big = count_words(c.text) > 800
        # Only a chunk holding one oversized paragraph may pass the limit.
        assert not too_big or any(count_words(p) > 800 - count_words(c.heading_path) and p in c.text for p in paragraphs)


def test_a_large_book_chunks_quickly():
    pages, _ = _random_book(random.Random(99), n_lessons=60)

    chunks = chunk(pages)

    assert len(chunks) > 60
