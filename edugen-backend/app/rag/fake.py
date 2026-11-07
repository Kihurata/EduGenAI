"""Tóm tắt: bộ sinh câu giả cho Backend (T-028), cùng chữ ký với hàm generate(cell) của make_generator() nhưng lấy câu từ một danh sách cố định thay vì gọi Qdrant/LLM, để Backend viết test và chạy demo không cần mô hình; FakeChunkLookup (T-029) tra đoạn trích dẫn từ file cố định thay vì Qdrant."""

import copy
import json
from pathlib import Path


class FakeGenerator:
    """generate(cell) -> (valid, []) from a fixed question list; never pads when fewer than count exist."""

    def __init__(self, questions):
        self.questions = list(questions)
        self.calls = []

    @classmethod
    def from_file(cls, path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def __call__(self, cell):
        self.calls.append(cell)
        same_type = [q for q in self.questions if q["type"] == cell["type"]]
        # sorted() is stable: same-topic questions first, bank order kept within each group.
        picked = sorted(same_type, key=lambda q: q.get("topic") != cell["topic"])[:cell["count"]]
        # Deep copies so the caller can edit questions without changing the bank.
        return [copy.deepcopy(q) | {"level": cell["level"], "topic": cell["topic"]} for q in picked], []


class FakeChunkLookup:
    """lookup(ids) -> (found {id: chunk dict}, missing [id]) from a fixed chunk list, like make_chunk_lookup()."""

    def __init__(self, chunks):
        self.chunks = {c["id"]: c for c in chunks}

    @classmethod
    def from_file(cls, path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def __call__(self, ids):
        found = {i: dict(self.chunks[i]) for i in ids if i in self.chunks}
        return found, [i for i in ids if i not in found]
