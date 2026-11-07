"""Tóm tắt: các quy ước Markdown SGK dùng chung cho mọi bộ cắt đoạn: đọc pages.md (dấu "{N}----" trước mỗi trang), đề mục # Chương / ## Bài / ### Mục, đường dẫn đề mục "Toán 12 > Chương > Bài > Mục", và đếm token bằng tokenizer bge-m3."""

import re
from functools import lru_cache
from pathlib import Path

from app.core.subjects import SUBJECTS

SUBJECT_NAMES = {s.code: s.label for s in SUBJECTS.values()}  # tên ngắn của môn, từ registry (D-020)
HEADING = re.compile(r"^(#{1,3}) (.+?)\s*$")  # level 1 Chương, 2 Bài, 3 Mục; deeper levels are paragraph text
_PAGE = re.compile(r"^\{(\d+)\}-{10,}\s*$", re.MULTILINE)


def read_pages_md(path):
    """Marker-style pages.md ("{N}----" before each page) -> [(page, markdown)]."""
    parts = _PAGE.split(Path(path).read_text(encoding="utf-8"))
    return [(int(n), md.strip()) for n, md in zip(parts[1::2], parts[2::2])]


def heading_path(subject, grade, titles):
    """("Chương I", "Bài 1", "") -> "Toán 12 > Chương I > Bài 1"; empty titles are skipped."""
    return " > ".join([f"{SUBJECT_NAMES[subject]} {grade}"] + [t for t in titles if t])


@lru_cache(maxsize=1)
def _tokenizer():
    from tokenizers import Tokenizer  # a core dependency (no torch, unlike transformers): ingest needs it without the embed extra

    return Tokenizer.from_pretrained("BAAI/bge-m3")


def bge_m3_token_count(text):
    return len(_tokenizer().encode(text, add_special_tokens=False).ids)
