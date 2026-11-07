"""Tóm tắt: tạo embedding bằng mô hình bge-m3 chạy trên máy: mỗi đoạn ra một vector dense (1024 số) và một vector sparse (trọng số từ khoá)."""

from app.rag.dto import Vector


class BgeM3Embedder:
    def __init__(self, model="BAAI/bge-m3"):
        from FlagEmbedding import BGEM3FlagModel  # slow import (torch); keep it out of unit tests

        self.model = BGEM3FlagModel(model, use_fp16=False)

    def embed(self, texts: list[str]) -> list[Vector]:
        out = self.model.encode(texts, return_dense=True, return_sparse=True)
        return [
            Vector(dense=dense.tolist(), sparse={int(k): float(w) for k, w in weights.items()})
            for dense, weights in zip(out["dense_vecs"], out["lexical_weights"])
        ]

    def embed_query(self, text: str) -> Vector:
        return self.embed([text])[0]
