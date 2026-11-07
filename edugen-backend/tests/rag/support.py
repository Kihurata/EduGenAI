"""Tóm tắt: dữ liệu và hàm dựng dùng chung cho test RAG (đường dẫn fixture, đoạn lý thuyết/đề mẫu giả, ô ma trận, câu trả lời mẫu của LLM, trang SGK giả), để các file test không phải import lẫn nhau."""

import json
from pathlib import Path

from qdrant_client import QdrantClient

from app.rag.dto import Chunk
from app.rag.storage.qdrant import index_chunks
from app.rag.vocab import PART_BY_TYPE
from tests.rag.fakes import FakeEmbedder

RAG_TESTS = Path(__file__).parent
FIXTURES = RAG_TESTS / "fixtures"
BACKEND = RAG_TESTS.parents[1]
INDEX = BACKEND / "qdrant_data"  # real index (git-ignored), used by acceptance / eval only

EXAMS = FIXTURES / "toan-tn"
EXAM_2025 = EXAMS / "toan-tn-2025-0101.json"
EXAM_REF_2025 = EXAMS / "toan-tn-2025-tham-khao.json"
EXAM_2026 = EXAMS / "toan-tn-2026-0102.json"
ALL_EXAMS = (EXAM_2025, EXAM_REF_2025, EXAM_2026)
CONTRACT = FIXTURES / "contract"
RETRIEVAL = FIXTURES / "rag-retrieval"

DAO_HAM = "dai_so_giai_tich/ung_dung_dao_ham"
XAC_SUAT = "thong_ke_xac_suat/xac_suat_co_dien"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def words(n, tag="w"):
    """n distinct words; with `count_words` as the token counter, a text of n words is n tokens."""
    return " ".join(f"{tag}{i}" for i in range(n))


def count_words(text):
    return len(text.split())


def theory(i, subject="toan", lesson="Bài 1", kind="theory", page=None, chapter="Chương I"):
    return Chunk(id=f"t{i}", kind=kind, text=f"{subject} {lesson} doan {i}", subject=subject, grade=12,
                 chapter=chapter, lesson=lesson, section=f"Mục {i}", heading_path=f"{lesson} > Mục {i}",
                 source="sgk.pdf", page=i if page is None else page, official=True)


def exam_item(i, topic=DAO_HAM, part="I", subject="toan"):
    return Chunk(id=f"e{i}", kind="exam_item", text=f"Câu {i} {topic}", subject=subject, grade=12,
                 chapter="", lesson="", section="", heading_path=f"Phần {part} > Câu {i}", source="de.json",
                 page=None, official=True, year=2025, exam_code="0101", part=part, question_no=i, topic=topic,
                 type={v: t for t, v in PART_BY_TYPE.items()}[part])


def memory_client(chunks=()):
    client = QdrantClient(":memory:")
    if chunks:
        index_chunks(client, list(chunks), FakeEmbedder())
    return client


def cell(qtype="multiple_choice", count=1, topic=DAO_HAM, level="Biết", **extra):
    return {"subject": "toan", "topic": topic, "level": level, "type": qtype, "count": count} | extra


# What the LLM returns for each question type (structured-output shape), citing theory chunk t1 / t2.
LLM_OUTPUT = {
    "multiple_choice": {"stem": "Đạo hàm của $x^2$ là", "options": {"A": "$2x$", "B": "$x$", "C": "$2$", "D": "$x^2$"},
                        "answer": "A", "explanation": "$(x^2)'=2x$", "source_chunk_ids": ["t1"], "sympy": {"expr": None}},
    "true_false": {"stem": "Cho $f(x)=x^3$.",
                   "statements": [{"label": x, "text": f"ý {x}", "answer": x == "a"} for x in "abcd"],
                   "explanation": "...", "source_chunk_ids": ["t2"]},
    "short_answer": {"stem": "Tính $f'(1)$ với $f(x)=x^2$.", "answer": "2", "explanation": "...",
                     "source_chunk_ids": ["t1", "t2"], "sympy": {"expr": "diff(x**2, x).subs(x, 1)"}},
}


def reply(*questions):
    """The JSON text an LLM returns for these questions."""
    return json.dumps({"questions": list(questions)}, ensure_ascii=False)


def sgk_pages_md(path, lessons):
    """Write a marker-style pages.md: lessons = [(chapter, lesson, [(section, body)])], one page per lesson."""
    parts = []
    for page, (chapter, lesson, sections) in enumerate(lessons, start=1):
        md = f"# {chapter}\n\n## {lesson}\n\n" + "\n\n".join(f"### {t}\n\n{b}" for t, b in sections)
        parts.append("{" + str(page) + "}" + "-" * 48 + "\n\n" + md + "\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")
    return path
