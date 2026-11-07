"""Tóm tắt: unit test lưu đoạn vào Qdrant (D-004) trên Qdrant trong bộ nhớ: collection có vector dense 1024 cosine + sparse, ghi lại không nhân đôi mà cập nhật, payload = Chunk.to_dict(), một client dùng chung cho cả tiến trình (Qdrant server/Cloud khi có QDRANT_URL, T-049); thêm test áp lực với hàng nghìn đoạn."""

import uuid

import pytest
from qdrant_client import models

from app.rag.chunking.exam import chunk_exam
from app.rag.dto import Vector
from app.rag.storage import qdrant
from app.rag.storage.qdrant import COLLECTION, create_collection, index_chunks, point_id, sparse_vector
from tests.rag.fakes import FakeEmbedder
from tests.rag.support import EXAM_2025, memory_client, theory


class CountingEmbedder(FakeEmbedder):
    def __init__(self):
        self.batches = []

    def embed(self, texts):
        self.batches.append(list(texts))
        return super().embed(texts)


# --- existing behaviour (T-005) --------------------------------------------------------------------------------

def test_chunks_collection_has_dense_and_sparse_vectors():
    client = memory_client()

    create_collection(client)

    params = client.get_collection(COLLECTION).config.params
    dense = params.vectors["dense"]
    assert dense.size == 1024
    assert dense.distance == models.Distance.COSINE
    assert "sparse" in params.sparse_vectors


def test_create_collection_twice_keeps_existing_points():
    client = memory_client(chunk_exam(EXAM_2025)[:3])

    create_collection(client)

    assert client.count(COLLECTION).count == 3


def test_indexing_same_chunks_twice_does_not_duplicate_points():
    client = memory_client()
    chunks = chunk_exam(EXAM_2025)

    index_chunks(client, chunks, FakeEmbedder())
    index_chunks(client, chunks, FakeEmbedder())

    assert client.count(COLLECTION).count == 22


def test_indexed_point_has_contract_payload_and_both_vectors():
    client = memory_client()
    chunk = chunk_exam(EXAM_2025)[0]

    index_chunks(client, [chunk], FakeEmbedder())

    point = client.scroll(COLLECTION, with_vectors=True)[0][0]
    assert point.payload == chunk.to_dict()
    assert len(point.vector["dense"]) == 1024
    assert len(point.vector["sparse"].indices) > 0


# --- ids and vectors -------------------------------------------------------------------------------------------

def test_point_id_is_a_stable_uuid_of_the_chunk_id():
    assert point_id("abc") == point_id("abc") == str(uuid.uuid5(uuid.NAMESPACE_URL, "abc"))
    assert point_id("abc") != point_id("abd")
    uuid.UUID(point_id("x"))  # valid UUID string


def test_sparse_vector_keeps_indices_and_weights_aligned():
    sv = sparse_vector(Vector(dense=[], sparse={7: 0.5, 3: 1.5, 900: 0.1}))

    assert dict(zip(sv.indices, sv.values)) == {7: 0.5, 3: 1.5, 900: 0.1}


def test_stored_vectors_are_the_embedder_output():
    client = memory_client()
    chunk = theory(1)
    [expected] = FakeEmbedder().embed([chunk.text])

    index_chunks(client, [chunk], FakeEmbedder())

    point = client.scroll(COLLECTION, with_vectors=True)[0][0]
    norm = sum(x * x for x in expected.dense) ** 0.5  # cosine collections store the unit vector
    assert point.vector["dense"] == pytest.approx([x / norm for x in expected.dense], rel=1e-4)
    assert dict(zip(point.vector["sparse"].indices, point.vector["sparse"].values)) == expected.sparse


# --- write behaviour -------------------------------------------------------------------------------------------

def test_reindexing_a_changed_chunk_updates_it_in_place():
    client = memory_client([theory(1)])
    changed = theory(1)
    changed.text = "nội dung mới"

    index_chunks(client, [changed], FakeEmbedder())

    [point] = client.scroll(COLLECTION)[0]
    assert client.count(COLLECTION).count == 1 and point.payload["text"] == "nội dung mới"


def test_all_texts_are_embedded_in_one_batch_in_chunk_order():
    embedder = CountingEmbedder()
    chunks = [theory(i) for i in range(5)]

    index_chunks(memory_client(), chunks, embedder)

    assert embedder.batches == [[c.text for c in chunks]]


def test_point_is_found_by_its_chunk_id():
    chunk = chunk_exam(EXAM_2025)[5]
    client = memory_client([chunk])

    [point] = client.retrieve(COLLECTION, [point_id(chunk.id)])

    assert point.payload["id"] == chunk.id


def test_indexing_into_an_existing_collection_adds_points():
    client = memory_client([theory(1)])

    index_chunks(client, [theory(2)], FakeEmbedder())

    assert client.count(COLLECTION).count == 2


# --- the shared client -----------------------------------------------------------------------------------------

def _open_default_client(monkeypatch, **env):
    for name in ("QDRANT_URL", "QDRANT_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    opened = []
    monkeypatch.setattr(qdrant, "QdrantClient", lambda **kw: opened.append(kw) or object())
    qdrant.default_client.cache_clear()
    try:
        assert qdrant.default_client() is qdrant.default_client()
    finally:
        qdrant.default_client.cache_clear()
    return opened


def test_default_client_is_opened_once_per_process(monkeypatch):
    assert _open_default_client(monkeypatch) == [{"path": str(qdrant.INDEX)}]


def test_default_client_uses_the_qdrant_server_when_qdrant_url_is_set(monkeypatch):
    """T-049 / D-012: Qdrant Cloud (or a Docker server) via QDRANT_URL + QDRANT_API_KEY instead of qdrant_data/."""
    opened = _open_default_client(monkeypatch, QDRANT_URL="https://abc.cloud.qdrant.io:6333", QDRANT_API_KEY="k")

    assert opened == [{"url": "https://abc.cloud.qdrant.io:6333", "api_key": "k"}]


def test_qdrant_server_without_api_key_is_allowed_for_a_local_docker_server(monkeypatch):
    opened = _open_default_client(monkeypatch, QDRANT_URL="http://localhost:6333")

    assert opened == [{"url": "http://localhost:6333", "api_key": None}]


def test_default_index_lives_next_to_the_backend_project():
    assert qdrant.INDEX.name == "qdrant_data" and (qdrant.INDEX.parent / "pyproject.toml").exists()


# --- stress ----------------------------------------------------------------------------------------------------

def test_two_thousand_chunks_index_and_reindex_without_duplicates():
    client = memory_client()
    chunks = [theory(i, lesson=f"Bài {i % 20}") for i in range(2000)]

    index_chunks(client, chunks, FakeEmbedder())
    index_chunks(client, chunks[:500], FakeEmbedder())

    assert client.count(COLLECTION).count == 2000


def test_school_id_has_a_keyword_index(monkeypatch):
    client = memory_client()
    indexed = {}
    monkeypatch.setattr(client, "create_payload_index", lambda _c, field, schema: indexed.update({field: schema}))
    create_collection(client)
    assert indexed["school_id"] == models.PayloadSchemaType.KEYWORD


@pytest.mark.parametrize("field", ["type", "exam_kind", "level"])
def test_t034_exam_item_fields_have_a_keyword_index(monkeypatch, field):
    client = memory_client()
    indexed = {}
    monkeypatch.setattr(client, "create_payload_index", lambda _c, f, schema: indexed.update({f: schema}))
    create_collection(client)
    assert indexed[field] == models.PayloadSchemaType.KEYWORD


@pytest.mark.parametrize("field, schema", [("source", models.PayloadSchemaType.KEYWORD),
                                           ("year", models.PayloadSchemaType.INTEGER)])
def test_t049_every_filtered_field_has_an_index_because_qdrant_cloud_rejects_unindexed_filters(monkeypatch, field, schema):
    """Qdrant Cloud answers 400 "Index required" for a filter on an unindexed field (seen 2026-11-05):
    `source` (re-upload deletes a file's old chunks) and `year` (exclude_year in retrieve)."""
    client = memory_client()
    indexed = {}
    monkeypatch.setattr(client, "create_payload_index", lambda _c, f, schema: indexed.update({f: schema}))
    create_collection(client)
    assert indexed[field] == schema


# --- BM25 collections (T-048) ----------------------------------------------------------------------------------

class IdfEmbedder(FakeEmbedder):
    sparse_idf = True


def test_a_bm25_embedder_gets_a_sparse_vector_with_idf():
    client = memory_client()

    index_chunks(client, chunk_exam(EXAM_2025)[:2], IdfEmbedder())

    assert client.get_collection(COLLECTION).config.params.sparse_vectors["sparse"].modifier == models.Modifier.IDF


def test_bge_m3_style_sparse_vectors_get_no_idf():
    client = memory_client()

    create_collection(client)

    assert client.get_collection(COLLECTION).config.params.sparse_vectors["sparse"].modifier in (None, models.Modifier.NONE)


@pytest.mark.parametrize("built_with, used_with", [(FakeEmbedder, IdfEmbedder), (IdfEmbedder, FakeEmbedder)])
def test_an_index_built_with_the_other_embedder_is_refused(built_with, used_with):
    client = memory_client()
    index_chunks(client, chunk_exam(EXAM_2025)[:2], built_with())

    with pytest.raises(qdrant.IndexMismatch, match="re-ingest"):
        qdrant.check_index(client, used_with())
    with pytest.raises(qdrant.IndexMismatch):
        index_chunks(client, chunk_exam(EXAM_2025)[2:4], used_with())


def test_a_missing_collection_matches_any_embedder():
    qdrant.check_index(memory_client(), IdfEmbedder())


class _CloudCollection:
    """Qdrant Cloud stand-in: reports the payload indexes it has and records the ones created (embedded Qdrant keeps none)."""

    def __init__(self, indexed):
        self.indexed, self.created = set(indexed), []

    def collection_exists(self, name):
        return True

    def get_collection(self, name):
        from types import SimpleNamespace

        return SimpleNamespace(payload_schema={f: None for f in self.indexed})

    def create_payload_index(self, name, field, schema):
        self.created.append((field, schema))
        self.indexed.add(field)


def test_missing_payload_indexes_are_added_to_an_existing_collection():
    from app.rag.storage.qdrant import ensure_payload_indexes

    cloud = _CloudCollection({"kind", "subject", "school_id"})
    ensure_payload_indexes(cloud)

    created = dict(cloud.created)
    assert created["teacher_id"] == models.PayloadSchemaType.KEYWORD and created["official"] == models.PayloadSchemaType.BOOL
    assert "kind" not in created  # existing indexes are left alone
    ensure_payload_indexes(cloud)
    assert len(cloud.created) == len(created)  # second run adds nothing
