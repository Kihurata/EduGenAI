"""Tóm tắt: lệnh nạp tài liệu vào Qdrant (T-005, T-003): đọc file (đề thi .json hoặc SGK đã đọc thành pages.md) → cắt đoạn (chunking) → embedding → ghi Qdrant (storage). Chạy: python -m app.rag.ingest <file> ... (dữ liệu lưu ở qdrant_data/), hoặc theo danh mục: python -m app.rag.ingest --sources [data/sources.yaml] (T-035)."""

import sys
from pathlib import Path

from app.rag.chunking import chunk_file
from app.rag.embedding import Embedder
from app.rag.storage.qdrant import index_chunks


def ingest(paths, client, embedder: Embedder, count_tokens=None):
    for path in map(Path, paths):
        chunks = chunk_file(path, count_tokens)
        index_chunks(client, chunks, embedder)
        print(f"{path.name}: {len(chunks)} chunks")


if __name__ == "__main__":
    from app.rag.embedding import make_embedder
    from app.rag.storage.qdrant import default_client

    client = default_client()
    if sys.argv[1:2] == ["--sources"]:  # T-035: the manifest, data/sources.yaml by default
        from app.rag.manifest import MANIFEST, ingest_sources
        ingest_sources(sys.argv[2] if len(sys.argv) > 2 else MANIFEST, client, make_embedder())
    else:
        ingest(sys.argv[1:], client, make_embedder())
    client.close()  # closing at interpreter exit prints a traceback
