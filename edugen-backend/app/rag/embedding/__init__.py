"""Tóm tắt: bước nhúng: giao diện Embedder mà lưu trữ và truy xuất dùng (embed cho tài liệu, embed_query cho câu tìm kiếm); make_embedder chọn bản thật theo biến EMBEDDER: gemini (mặc định, D-011) hoặc bge-m3; test dùng bản giả."""

import os
from typing import Protocol

from app.rag.dto import Vector


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[Vector]: ...

    def embed_query(self, text: str) -> Vector: ...


def make_embedder() -> Embedder:
    """EMBEDDER=gemini (default) | bge-m3. The index must be built with the same one (storage.qdrant.check_index)."""
    name = os.environ.get("EMBEDDER", "gemini")
    if name == "gemini":
        from app.rag.embedding.gemini_bm25 import GeminiBm25Embedder
        return GeminiBm25Embedder()
    if name == "bge-m3":
        from app.rag.embedding.bge_m3 import BgeM3Embedder
        return BgeM3Embedder()
    raise ValueError(f"unknown EMBEDDER {name!r}; use gemini or bge-m3")
