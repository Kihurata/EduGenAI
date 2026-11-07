"""Tóm tắt: feature test luồng nạp tài liệu (F-01, T-005): file SGK pages.md và đề thi JSON → ingest → Qdrant, rồi truy xuất và tra cứu lại được đúng đoạn; chạy lại không trùng, thứ tự nạp không đổi kết quả, file lạ dừng lại sau khi đã nạp các file trước; thêm test áp lực với sách lớn và cả ba đề. Chỉ thay mô hình nhúng bằng bản giả, còn lại là code thật."""

import re

import pytest

from app.rag.ingest import ingest
from app.rag.storage.lookup import make_chunk_lookup
from app.rag.storage.qdrant import COLLECTION, point_id
from app.rag.storage.retrieve import retrieve
from tests.rag.fakes import FakeEmbedder
from tests.rag.support import ALL_EXAMS, DAO_HAM, EXAM_2025, count_words, memory_client, sgk_pages_md, words

LESSONS = [
    ("Chương I. Ứng dụng đạo hàm", "Bài 1. Tính đơn điệu và cực trị",
     [("1. Tính đơn điệu", words(200, "a")), ("2. Cực trị", words(200, "b")), ("Bài tập", "**1.1.** " + words(150, "e"))]),
    ("Chương I. Ứng dụng đạo hàm", "Bài 2. Giá trị lớn nhất, nhỏ nhất",
     [("1. Định nghĩa", words(200, "c"))]),
    ("Chương II. Vectơ trong không gian", "Bài 6. Vectơ", [("1. Khái niệm", words(200, "d"))]),
]


@pytest.fixture
def sgk(tmp_path):
    return sgk_pages_md(tmp_path / "sgk-toan-12-kntt-tap-1" / "manual" / "pages.md", LESSONS)


def _ingest(paths, client=None):
    client = client or memory_client()
    ingest(paths, client, FakeEmbedder(), count_tokens=count_words)
    return client


def _payloads(client):
    return [p.payload for p in client.scroll(COLLECTION, limit=10_000)[0]]


# --- existing behaviour ----------------------------------------------------------------------------------------

def test_ingest_exam_json_twice_keeps_22_points():
    client = _ingest([EXAM_2025])
    _ingest([EXAM_2025], client)

    assert client.count(COLLECTION).count == 22


def test_ingest_parsed_sgk_pages_md_as_theory_chunks(tmp_path):
    md = sgk_pages_md(tmp_path / "sgk-toan-12" / "manual" / "pages.md",
                      [("Chương I. X", "Bài 1. Y", [("1. A", words(150)), ("2. B", words(150))])])

    client = _ingest([md])

    payloads = _payloads(client)
    assert [p["section"] for p in payloads if p["kind"] == "theory"] != []
    assert {p["source"] for p in payloads} == {"sgk-toan-12.pdf"}
    assert client.count(COLLECTION).count == 2


def test_ingest_rejects_unknown_file_type(tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("x")

    with pytest.raises(ValueError, match="notes.txt"):
        _ingest([notes])


# --- a book and the official exams together --------------------------------------------------------------------

def test_book_and_exams_land_in_one_collection(sgk):
    client = _ingest([sgk, *ALL_EXAMS])

    kinds = [p["kind"] for p in _payloads(client)]
    assert kinds.count("exam_item") == 66
    assert kinds.count("exercise") == 1 and kinds.count("theory") == 4


def test_every_ingested_chunk_can_be_looked_up_by_its_id(sgk):
    client = _ingest([sgk, EXAM_2025])
    ids = [p["id"] for p in _payloads(client)]

    found, missing = make_chunk_lookup(client)(ids)

    assert missing == [] and len(found) == len(ids)


def test_theory_of_a_lesson_is_retrievable_with_page_and_heading(sgk):
    client = _ingest([sgk])

    theory, _ = retrieve(client, FakeEmbedder(), {"subject": "toan", "topic": DAO_HAM, "type": "multiple_choice",
                                                  "lesson": "Bài 2. Giá trị lớn nhất, nhỏ nhất"})

    assert [(c.lesson, c.page, c.section) for c in theory] == [("Bài 2. Giá trị lớn nhất, nhỏ nhất", 2, "1. Định nghĩa")]
    assert theory[0].heading_path == "Toán 12 > Chương I. Ứng dụng đạo hàm > Bài 2. Giá trị lớn nhất, nhỏ nhất > 1. Định nghĩa"


def test_exercises_are_stored_but_never_retrieved_as_theory(sgk):
    client = _ingest([sgk])

    theory, _ = retrieve(client, FakeEmbedder(), {"subject": "toan", "topic": DAO_HAM, "type": "multiple_choice"}, k=50)

    assert all(c.kind == "theory" for c in theory) and len(theory) == 4


@pytest.mark.parametrize("qtype, part, n", [("multiple_choice", "I", 12), ("true_false", "II", 4), ("short_answer", "III", 6)])
def test_every_exam_item_is_retrievable_by_its_topic_and_part(qtype, part, n):
    from app.rag.chunking.exam import chunk_exam
    from app.rag.vocab import OLD_TO_NEW

    client = _ingest([EXAM_2025])
    items = [c for c in chunk_exam(EXAM_2025) if c.part == part]

    for item in items:
        topic = OLD_TO_NEW.get(item.topic, item.topic)
        _, exam_items = retrieve(client, FakeEmbedder(), {"subject": "toan", "topic": topic, "type": qtype}, k=50)
        assert item.id in {e.id for e in exam_items}, (part, item.question_no, item.topic)
    assert len(items) == n


# --- re-running and ordering -----------------------------------------------------------------------------------

def test_reingesting_everything_changes_nothing(sgk):
    client = _ingest([sgk, *ALL_EXAMS])
    before = sorted((p["id"], p["text"]) for p in _payloads(client))

    _ingest([sgk, *ALL_EXAMS], client)

    assert sorted((p["id"], p["text"]) for p in _payloads(client)) == before


def test_ingest_order_does_not_change_the_index(sgk):
    a = _ingest([sgk, EXAM_2025])
    b = _ingest([EXAM_2025, sgk])

    assert sorted(p["id"] for p in _payloads(a)) == sorted(p["id"] for p in _payloads(b))


def _edit_first_lesson(sgk):
    """Rewrite Bài 1 to a single section; the other lessons stay word-for-word the same."""
    return sgk_pages_md(sgk, [(LESSONS[0][0], LESSONS[0][1], [("1. Tính đơn điệu", words(200, "z"))])] + LESSONS[1:])


def _has_word(texts, word):
    return any(re.search(rf"\b{word}\b", t) for t in texts)


def test_reingesting_an_edited_book_replaces_a_section_edited_in_place(sgk):
    client = _ingest([sgk])

    _ingest([_edit_first_lesson(sgk)], client)

    texts = [p["text"] for p in _payloads(client)]
    assert _has_word(texts, "z0") and not _has_word(texts, "a0")  # same source, page, heading, position → same id


def test_sections_removed_from_a_book_stay_in_the_index(sgk):
    client = _ingest([sgk])

    _ingest([_edit_first_lesson(sgk)], client)

    assert _has_word([p["text"] for p in _payloads(client)], "b0")  # "2. Cực trị" is gone from the book, not the index


def test_reingesting_an_edited_book_does_not_duplicate_unchanged_lessons(sgk):
    client = _ingest([sgk])

    _ingest([_edit_first_lesson(sgk)], client)

    sections = [p["section"] for p in _payloads(client) if p["lesson"] != LESSONS[0][1]]
    assert sorted(sections) == ["1. Khái niệm", "1. Định nghĩa"]


def test_a_bad_file_stops_ingest_after_the_files_before_it(sgk, tmp_path):
    bad = tmp_path / "scan.pdf"
    bad.write_bytes(b"%PDF")
    client = memory_client()

    with pytest.raises(ValueError, match="scan.pdf"):
        ingest([EXAM_2025, bad, sgk], client, FakeEmbedder(), count_tokens=count_words)

    assert client.count(COLLECTION).count == 22  # the exam went in, the book after the bad file did not


def test_ingest_prints_one_line_per_file(sgk, capsys):
    _ingest([sgk, EXAM_2025])

    assert capsys.readouterr().out.splitlines() == ["pages.md: 5 chunks", "toan-tn-2025-0101.json: 22 chunks"]


def test_ingest_accepts_string_paths(sgk):
    assert _ingest([str(sgk), str(EXAM_2025)]).count(COLLECTION).count == 27


def test_ingesting_nothing_is_a_no_op():
    client = memory_client()

    ingest([], client, FakeEmbedder())

    assert not client.collection_exists(COLLECTION)


def test_the_stored_point_id_is_derived_from_the_chunk_id(sgk):
    client = _ingest([sgk])

    for p in client.scroll(COLLECTION, limit=100)[0]:
        assert p.id == point_id(p.payload["id"])


# --- stress ----------------------------------------------------------------------------------------------------

def test_a_full_size_book_and_every_exam(tmp_path):
    lessons = [(f"Chương {c}", f"Bài {c}.{b}", [(f"{s}. Mục {s}", words(300, f"c{c}b{b}s{s}_")) for s in range(1, 5)])
               for c in range(1, 7) for b in range(1, 5)]
    book = sgk_pages_md(tmp_path / "big-book" / "marker" / "pages.md", lessons)

    client = _ingest([book, *ALL_EXAMS])
    _ingest([book, *ALL_EXAMS], client)

    assert client.count(COLLECTION).count == 24 * 4 + 66
    theory, items = retrieve(client, FakeEmbedder(), {"subject": "toan", "topic": DAO_HAM, "type": "true_false",
                                                      "lesson": "Bài 3.2"}, k=10)
    assert len(theory) == 4 and {c.lesson for c in theory} == {"Bài 3.2"}
    assert items and all(i.part == "II" for i in items)
