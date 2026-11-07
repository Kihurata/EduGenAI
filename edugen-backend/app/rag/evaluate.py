"""Tóm tắt: đo chất lượng truy xuất (T-007): recall@k trên golden set, tức tỉ lệ câu hỏi có ít nhất một đoạn lý thuyết thuộc bài mong đợi trong k kết quả đầu. Dòng không có "query" thì chỉ dùng ô ma trận (TC-014). `compare_chunkers` cho bảng 2×2 của T-007: cắt theo đề mục vs cắt cố định × lai vs dense."""

from qdrant_client import QdrantClient

from app.rag.chunking.fixed import chunk_fixed
from app.rag.chunking.theory import chunk_theory
from app.rag.storage.qdrant import index_chunks
from app.rag.storage.retrieve import retrieve

CHUNKERS = {"heading": chunk_theory, "fixed": chunk_fixed}
MODES = ("hybrid", "dense")


def recall_at_k(client, embedder, golden, k=5, mode="hybrid"):
    """golden rows: {optional "query", "cell", "expected_lessons"}; a hit = an expected lesson title inside a top-k chunk's `lesson`."""
    hits = 0
    for row in golden:
        theory, _ = retrieve(client, embedder, row["cell"] | {"query": row.get("query")}, k=k, mode=mode)
        hits += any(lesson in c.lesson for c in theory for lesson in row["expected_lessons"])
    return hits / len(golden)


def compare_chunkers(pages, source, golden, embedder, k=5, count_tokens=None, max_tokens=800):
    """T-007: -> {(chunker, mode): recall@k}, each chunker in its own in-memory index, same token limit for both."""
    result = {}
    for name, chunker in CHUNKERS.items():
        client = QdrantClient(":memory:")
        index_chunks(client, chunker(pages, source, count_tokens=count_tokens, max_tokens=max_tokens), embedder)
        for mode in MODES:
            result[(name, mode)] = recall_at_k(client, embedder, golden, k=k, mode=mode)
    return result


def format_table(result):
    rows = ["chunker   hybrid  dense"]
    rows += [f"{name:<9}{result[(name, 'hybrid')]:>7.0%}{result[(name, 'dense')]:>7.0%}" for name in CHUNKERS]
    return "\n".join(rows)
