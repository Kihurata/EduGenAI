"""Tóm tắt: bộ cắt đoạn cố định (T-003), chỉ dùng làm mốc so sánh trong T-007: cắt SGK thành các cửa sổ tối đa max_tokens token, bỏ qua ranh giới đề mục; mỗi đoạn mang chương/bài/mục và trang nơi nó bắt đầu, để chấm recall theo `lesson` giống bộ cắt theo đề mục (theory.py)."""

import hashlib

from app.rag.chunking.markdown import HEADING, bge_m3_token_count, heading_path
from app.rag.dto import Chunk


def chunk_fixed(pages, source, subject="toan", grade=12, count_tokens=None, max_tokens=800):
    """pages: [(page, markdown)] -> theory Chunks of at most max_tokens (summed per word), cut anywhere.

    chapter / section / page come from where a window starts; `lesson` lists every lesson the window covers
    ("Bài 1 | Bài 2"), so recall counts a window for each lesson whose text it holds.
    """
    count = count_tokens or bge_m3_token_count
    titles, stream = ("", "", ""), []  # stream: (page, titles at that word, word)
    for page, md in pages:
        for line in md.splitlines():
            if heading := HEADING.match(line):
                level, line = len(heading.group(1)), heading.group(2)
                titles = titles[:level - 1] + (line,) + ("",) * (3 - level)
            stream += [(page, titles, word) for word in line.split()]

    windows, window, size = [], [], 0
    for item in stream:
        tokens = count(item[2])
        if window and size + tokens > max_tokens:
            windows.append(window)
            window, size = [], 0
        window.append(item)
        size += tokens
    if window:
        windows.append(window)
    return [_chunk(w, n, source, subject, grade) for n, w in enumerate(windows)]


def _chunk(window, n, source, subject, grade):
    page, (chapter, first_lesson, section), _ = window[0]
    lesson = " | ".join(dict.fromkeys(t[1] for _, t, _ in window if t[1]))
    return Chunk(
        id=hashlib.sha1(f"fixed|{source}|{n}".encode()).hexdigest()[:16], kind="theory",
        text=" ".join(word for *_, word in window), subject=subject, grade=grade, chapter=chapter, lesson=lesson,
        section=section, heading_path=heading_path(subject, grade, (chapter, first_lesson, section)), source=source,
        page=page, official=True,
    )
