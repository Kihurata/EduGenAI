"""Tóm tắt: unit test tra cứu đoạn theo ID trích dẫn (T-029) cho màn hình duyệt đề: trả đủ trường để hiển thị, ID lạ nằm trong danh sách thiếu (không lỗi), giữ thứ tự, ID trùng, danh sách rỗng, nhiều ID; mặc định dùng chung Qdrant client với bộ sinh câu."""

from app.rag import pipeline
from app.rag.storage import qdrant
from app.rag.storage.lookup import make_chunk_lookup
from tests.rag.fakes import FakeEmbedder, FakeLLM
from tests.rag.support import exam_item, memory_client, theory

FIELDS = ("heading_path", "page", "text", "source", "kind", "lesson")
THEORY = [theory(1), theory(2)]
EXAMS = [exam_item(1), exam_item(2, part="II")]


def _lookup():
    return make_chunk_lookup(memory_client(THEORY + EXAMS))


# --- existing behaviour ----------------------------------------------------------------------------------------

def test_lookup_returns_known_chunks_with_review_fields():
    found, missing = _lookup()([THEORY[0].id, EXAMS[0].id])

    assert missing == []
    for chunk in (THEORY[0], EXAMS[0]):
        assert {k: found[chunk.id][k] for k in FIELDS} == {k: getattr(chunk, k) for k in FIELDS}


def test_unknown_id_is_listed_missing_and_known_ones_still_returned():
    found, missing = _lookup()(["not-indexed", THEORY[1].id])

    assert list(found) == [THEORY[1].id]
    assert missing == ["not-indexed"]


def test_default_generator_and_lookup_share_one_qdrant_client(monkeypatch):
    """Local Qdrant locks its folder, so a second client on qdrant_data/ would fail."""
    created = []

    def fake_client(path):
        created.append(path)
        return memory_client(THEORY + EXAMS)

    monkeypatch.setattr(qdrant, "QdrantClient", fake_client)  # never opens qdrant_data/
    qdrant.default_client.cache_clear()
    try:
        pipeline.make_generator(embedder=FakeEmbedder(), llm=FakeLLM([]))
        assert len(created) == 1
        found, _ = make_chunk_lookup()([THEORY[0].id])
        assert len(created) == 1 and THEORY[0].id in found
    finally:
        qdrant.default_client.cache_clear()


# --- edge cases ------------------------------------------------------------------------------------------------

def test_no_ids_gives_nothing():
    assert _lookup()([]) == ({}, [])


def test_exam_items_keep_their_exam_fields():
    found, _ = _lookup()([EXAMS[1].id])

    assert {k: found[EXAMS[1].id][k] for k in ("part", "question_no", "topic", "year")} == {
        "part": "II", "question_no": 2, "topic": EXAMS[1].topic, "year": 2025}


def test_theory_chunks_have_no_exam_fields():
    found, _ = _lookup()([THEORY[0].id])

    assert "part" not in found[THEORY[0].id]


def test_missing_ids_keep_the_order_they_were_asked_in():
    _, missing = _lookup()(["z", THEORY[0].id, "a", "m"])

    assert missing == ["z", "a", "m"]


def test_a_duplicated_known_id_is_found_once():
    found, missing = _lookup()([THEORY[0].id, THEORY[0].id])

    assert list(found) == [THEORY[0].id] and missing == []


def test_a_duplicated_unknown_id_is_listed_each_time():
    assert _lookup()(["x", "x"])[1] == ["x", "x"]


def test_found_chunk_is_the_full_payload():
    found, _ = _lookup()([THEORY[0].id])

    assert found[THEORY[0].id] == THEORY[0].to_dict()


def test_lookup_on_an_empty_index_reports_everything_missing():
    client = memory_client()
    qdrant.create_collection(client)

    assert make_chunk_lookup(client)(["a", "b"]) == ({}, ["a", "b"])


# --- stress ----------------------------------------------------------------------------------------------------

def test_five_hundred_ids_half_unknown():
    chunks = [theory(i) for i in range(250)]
    lookup = make_chunk_lookup(memory_client(chunks))
    ids = [c.id for c in chunks] + [f"unknown-{i}" for i in range(250)]

    found, missing = lookup(ids)

    assert len(found) == 250 and len(missing) == 250 and set(missing) == set(ids[250:])


def test_lookup_before_anything_is_indexed_reports_everything_missing():
    """T-029 open item: a fresh qdrant_data/ has no collection yet; review must still open, with sources missing."""
    assert make_chunk_lookup(memory_client())(["a", "b"]) == ({}, ["a", "b"])
