"""Tóm tắt: đổi đề thi chính thức (JSON) sang dạng câu hỏi trong hợp đồng RAG → Backend (T-028): loại câu, mức độ, mã chủ đề mới, đoạn trích dẫn. Chạy: python -m app.rag.contract → ghi file mẫu tests/fixtures/contract/toan-22-questions.json và toan-22-chunks.json (các đoạn mà câu hỏi trích dẫn, cho FakeChunkLookup, T-029) cho Backend."""

import json
from pathlib import Path

from app.rag.chunking.exam import chunk_exam, exam_item_id
from app.rag.vocab import LEVELS, OLD_TO_NEW, PART_BY_TYPE

TYPE_BY_PART = {part: kind for kind, part in PART_BY_TYPE.items()}
_OPTIONAL = ("figure", "table")


def to_contract(exam, levels):
    """levels: {"I": {"1": "Hiểu", ...}, "II": {"1": [level of a, b, c, d], ...}, "III": {...}}."""
    out = []
    for q in exam["questions"]:
        level = levels[q["part"]][str(q["cau"])]
        c = {"type": TYPE_BY_PART[q["part"]], "part": q["part"], "cau": q["cau"], "stem": q["stem"]}
        c |= {key: q[key] for key in _OPTIONAL if key in q}
        if "statements" in q:
            c["statements"] = [s | {"level": lv} for s, lv in zip(q["statements"], level, strict=True)]
            level = max(level, key=LEVELS.index)  # a true/false question is as hard as its hardest statement
        else:
            c |= {key: q[key] for key in ("options", "answer") if key in q}
        c |= {"explanation": "", "level": level, "topic": OLD_TO_NEW[q["topic"]],
              "source_chunk_ids": [exam_item_id(f"{exam['id']}.json", q["part"], q["cau"])]}
        out.append(c)
    return out


if __name__ == "__main__":
    fixtures = Path("tests/rag/fixtures")
    exam_path = fixtures / "toan-tn/toan-tn-2025-0101.json"
    exam = json.loads(exam_path.read_text(encoding="utf-8"))
    levels = json.loads((fixtures / "contract/levels-toan-tn-2025-0101.json").read_text(encoding="utf-8"))
    questions = to_contract(exam, levels)
    cited = {i for q in questions for i in q["source_chunk_ids"]}
    chunks = [c.to_dict() for c in chunk_exam(exam_path) if c.id in cited]
    for name, data in (("toan-22-questions.json", questions), ("toan-22-chunks.json", chunks)):
        out = fixtures / "contract" / name
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {out}")
