"""Tóm tắt: LLM giả và bộ embedding giả cho unit test, trả kết quả cố định nên test không tốn tiền API và không cần tải mô hình."""

import hashlib

from app.rag.dto import Vector


class FakeLLM:
    """Returns the queued responses in order and records every prompt it got."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, system, prompt, **kwargs):
        self.calls.append({"system": system, "prompt": prompt, **kwargs})
        return self.responses.pop(0)


class FakeEmbedder:
    """Deterministic 1024-dim dense vector + tiny sparse vector derived from the text hash."""

    dim = 1024

    def embed(self, texts):
        out = []
        for text in texts:
            h = hashlib.sha256(text.encode("utf-8")).digest()
            dense = [h[i % len(h)] / 255 + 0.001 for i in range(self.dim)]
            sparse = {h[0]: 1.0, 256 + h[1]: 0.5}
            out.append(Vector(dense=dense, sparse=sparse))
        return out

    def embed_query(self, text):
        return self.embed([text])[0]
