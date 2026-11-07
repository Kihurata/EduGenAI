"""Tóm tắt: tạo collection `chunks` trong Qdrant (vector dense 1024 cosine + sparse của bge-m3, chỉ mục payload) và ghi đoạn vào đó theo D-004; ghi lại cùng đoạn thì cập nhật chứ không nhân đôi. `default_client` là Qdrant client dùng chung cho cả tiến trình: Qdrant server/Cloud khi có QDRANT_URL (D-012), không thì chế độ nhúng ở qdrant_data/ (thư mục bị khoá khi mở)."""

import logging
import os
import uuid
import warnings
from functools import cache
from pathlib import Path

from qdrant_client import QdrantClient, models

from app.rag.dto import Chunk, Vector
from app.rag.embedding import Embedder

INDEX = Path(__file__).parents[3] / "qdrant_data"
COLLECTION = "chunks"
DENSE_DIM = 1024
_KEYWORD_FIELDS = ("kind", "subject", "chapter", "lesson", "part", "topic", "school_id", "teacher_id", "type", "exam_kind", "level",
                   "source")  # every filtered field: Qdrant Cloud rejects filters on unindexed fields (T-049)
_PAYLOAD_INDEXES = {**dict.fromkeys(_KEYWORD_FIELDS, models.PayloadSchemaType.KEYWORD),
                    "grade": models.PayloadSchemaType.INTEGER, "year": models.PayloadSchemaType.INTEGER,
                    "official": models.PayloadSchemaType.BOOL}


def open_client():
    """QDRANT_URL (+ QDRANT_API_KEY) → Qdrant server/Cloud (D-012); unset → embedded qdrant_data/."""
    if url := os.environ.get("QDRANT_URL"):
        return QdrantClient(url=url, api_key=os.environ.get("QDRANT_API_KEY"))
    return QdrantClient(path=str(INDEX))


@cache
def default_client():
    """One client per process: local Qdrant locks qdrant_data/, so a second client on it fails."""
    return open_client()


def sparse_vector(v: Vector) -> models.SparseVector:
    return models.SparseVector(indices=list(v.sparse), values=list(v.sparse.values()))


class IndexMismatch(ValueError):
    """The index was built with the other embedder: its vectors can't be compared with this one's."""


def create_collection(client: QdrantClient, sparse_idf=False):
    if client.collection_exists(COLLECTION):
        return
    modifier = models.Modifier.IDF if sparse_idf else None  # BM25 (T-048) needs IDF; bge-m3 weights don't
    client.create_collection(
        COLLECTION,
        vectors_config={"dense": models.VectorParams(size=DENSE_DIM, distance=models.Distance.COSINE)},
        sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=modifier)},
    )
    ensure_payload_indexes(client)


def ensure_payload_indexes(client: QdrantClient):
    """Add the payload indexes the collection lacks: Qdrant Cloud rejects filters on unindexed fields (T-049), so a
    collection built before a new filter field (teacher_id, official) would fail every search using it."""
    have = client.get_collection(COLLECTION).payload_schema or {}
    with warnings.catch_warnings():  # embedded Qdrant keeps no payload indexes and warns on each one
        warnings.filterwarnings("ignore", message="Payload indexes have no effect")
        for field, schema in _PAYLOAD_INDEXES.items():
            if field not in have:
                client.create_payload_index(COLLECTION, field, schema)


def point_id(chunk_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def check_index(client: QdrantClient, embedder: Embedder):
    """Fail loudly when the index's sparse vectors were built for the other embedder (BM25 with IDF vs bge-m3)."""
    if not client.collection_exists(COLLECTION):
        return
    ensure_payload_indexes(client)  # runs at startup (rag_client, pipeline) and before every ingest
    modifier = client.get_collection(COLLECTION).config.params.sparse_vectors["sparse"].modifier
    built_idf = modifier == models.Modifier.IDF
    if built_idf != getattr(embedder, "sparse_idf", False):
        built, used = ("gemini", "bge-m3") if built_idf else ("bge-m3", "gemini")
        raise IndexMismatch(f"index in {COLLECTION!r} was built for {built}, EMBEDDER is {used}: re-ingest "
                            f"(python -m app.rag.ingest --sources) or set EMBEDDER={built}")


def warn_if_empty(client: QdrantClient):
    """Startup only (not ingest, where an empty index is normal): qdrant_data/ is gitignored and per worktree, so a fresh
    checkout starts fine with no collection and fails at the first generation."""
    if not client.collection_exists(COLLECTION) or not client.count(COLLECTION).count:
        logging.getLogger(__name__).warning(
            "index %r is missing or empty: generation will fail; ingest (python -m app.rag.ingest --sources ...) or set QDRANT_URL",
            COLLECTION)


def index_chunks(client: QdrantClient, chunks: list[Chunk], embedder: Embedder):
    check_index(client, embedder)
    create_collection(client, getattr(embedder, "sparse_idf", False))
    vectors = embedder.embed([c.text for c in chunks])
    client.upsert(COLLECTION, points=[
        models.PointStruct(
            id=point_id(c.id),
            vector={"dense": v.dense, "sparse": sparse_vector(v)},
            payload=c.to_dict(),
        )
        for c, v in zip(chunks, vectors)
    ])


def delete_school_points(client: QdrantClient, school_id: str | None, source: str | None = None):
    """T-046: delete one school's points (or one of its sample exams). Always scoped to school_id,
    so shared points (SGK, official exams: no school_id) can never match."""
    if not (school_id and school_id.strip()):
        raise ValueError("school_id is required: refusing to delete shared points")
    if not client.collection_exists(COLLECTION):
        return
    must = [models.FieldCondition(key="school_id", match=models.MatchValue(value=school_id))]
    if source:
        must.append(models.FieldCondition(key="source", match=models.MatchValue(value=source)))
    client.delete(COLLECTION, points_selector=models.FilterSelector(filter=models.Filter(must=must)))
