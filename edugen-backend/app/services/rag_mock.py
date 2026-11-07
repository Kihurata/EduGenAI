"""RAG giả lập từ file kết quả mẫu (edugen-lab/samples/ket_qua_mau.json).

Dùng trong test và khi chạy BE mà chưa có RAG (đặt RAG_MOCK_SAMPLES trong .env). Mỗi ô trả
đủ `count` câu mẫu cùng dạng, lặp vòng nếu thiếu mẫu, mức độ ghi lại theo ô.
"""

import copy
import json
from itertools import cycle, islice
from pathlib import Path
from typing import Any

from app.domain.cell import Cell
from app.domain.question import LEVEL_TO_RAG, TYPE_TO_RAG, Question, parse_question


class SampleRag:
    def __init__(self, samples: list[dict[str, Any]]) -> None:
        self.questions = [s["cau_hoi"] for s in samples]

    @classmethod
    def from_file(cls, path: str | Path) -> "SampleRag":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def generate(self, cell: Cell) -> tuple[list[Question], list[Question]]:
        same_type = [q for q in self.questions if q.get("dang") == TYPE_TO_RAG[cell.type]]
        if not same_type:
            return [], []
        same_level = [q for q in same_type if q.get("muc_do") == LEVEL_TO_RAG[cell.level]]
        picked = [copy.deepcopy(q) for q in islice(cycle(same_level or same_type), cell.count)]
        for q in picked:
            q["muc_do"] = LEVEL_TO_RAG[cell.level]
        return picked, []

    def validate(self, question: Question, cell: Cell | None) -> list[str]:
        return parse_question(question, cell)[1]

    def ingest(self, data: bytes, filename: str, meta: dict[str, Any]) -> str:
        return f"mock-{filename}"

    def ingest_status(self, job_id: str) -> tuple[str, str | None]:
        return "done", None  # giả lập: học xong ngay

    def delete(self, school_id: str, source: str | None = None) -> None:
        return None  # giả lập: không có chỉ mục để xoá
