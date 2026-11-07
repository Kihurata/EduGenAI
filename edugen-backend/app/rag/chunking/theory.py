"""Tóm tắt: cắt Markdown SGK thành đoạn lý thuyết (T-003) theo D-003: tách theo đề mục Chương (#) / Bài (##) / Mục (###), mỗi đoạn bắt đầu bằng đường dẫn đề mục; mục dài hơn 800 token cắt ở chỗ xuống đoạn, mục ngắn dưới 100 token gộp với mục bên cạnh; không bao giờ cắt giữa công thức $$...$$; mục Bài tập là kind exercise, không gộp với lý thuyết; khối có nhãn (Ví dụ + Giải, Luyện tập, ...) không bị cắt."""

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field

from app.rag.chunking.markdown import HEADING, bge_m3_token_count, heading_path, read_pages_md  # noqa: F401 (re-export)
from app.rag.dto import Chunk

_EXERCISE = re.compile(r"bài\s*tập", re.IGNORECASE)
# D-003: a labelled block runs from its bold label to the next label or heading and is never split.
_LABEL = re.compile(r"^\*\*(Ví dụ|HĐ|Luyện tập|Vận dụng|Định lí|Chú ý)")


@dataclass
class _Section:
    """One heading and the paragraphs under it."""

    titles: tuple[str, str, str]  # chapter, lesson, section
    heading: str  # the Markdown heading line, e.g. "### 1. Định nghĩa"
    kind: str  # theory | exercise
    paras: list[tuple[int, str]] = field(default_factory=list)  # (page, text)


@dataclass
class _Piece:
    """A future chunk: paragraphs of one section (plus any small neighbours merged in)."""

    sec: _Section
    path: str  # heading path, also the first line of the chunk text
    page: int
    body: list[str]

    @property
    def text(self):
        return _text(self.path, self.body)

    def paragraphs_for(self, other):
        """These paragraphs as they read inside `other`: led by this heading when the sections differ."""
        return ([self.sec.heading] if self.sec is not other.sec else []) + self.body

    def same_kind_and_titles(self, other, depth):
        """Same kind, and the same first `depth` titles (1 = chapter, 2 = chapter and lesson)."""
        return self.sec.kind == other.sec.kind and self.sec.titles[:depth] == other.sec.titles[:depth]


def chunk_theory(pages, source, subject="toan", grade=12, count_tokens=None, max_tokens=800, min_tokens=100):
    """pages: [(page, markdown)] from the parser -> theory Chunks."""
    count = count_tokens or bge_m3_token_count
    pieces = [piece for sec in _sections(_blocks(pages))
              for piece in _split(sec, heading_path(subject, grade, sec.titles), count, max_tokens)]
    _merge_small(pieces, count, min_tokens, max_tokens)

    chunks, seen = [], Counter()
    for p in pieces:
        chapter, lesson, section = p.sec.titles
        chunks.append(Chunk(
            id=_chunk_id(f"{source}|{p.page}|{p.path}", seen), kind=p.sec.kind, text=p.text, subject=subject,
            grade=grade, chapter=chapter, lesson=lesson, section=section, heading_path=p.path, source=source,
            page=p.page, official=True,
        ))
    return chunks


def _chunk_id(key, seen):
    """Stable across edits elsewhere in the book: n counts only the pieces with the same source, page and heading."""
    n, seen[key] = seen[key], seen[key] + 1
    return hashlib.sha1(f"{key}|{n}".encode()).hexdigest()[:16]


def _text(path, body):
    return "\n\n".join([path] + body)


def _blocks(pages):
    """-> [(page, text, heading_level)]: paragraphs split on blank lines, except inside $$...$$."""
    out = []
    for page, md in pages:
        cur = []
        for line in md.splitlines():
            heading = HEADING.match(line)
            in_math = "\n".join(cur).count("$$") % 2 == 1
            if not in_math and (heading or not line.strip()):
                if cur:
                    out.append((page, "\n".join(cur), 0))
                    cur = []
                if heading:
                    out.append((page, heading.group(2), len(heading.group(1))))
                continue
            cur.append(line)
        if cur:
            out.append((page, "\n".join(cur), 0))
    return out


def _sections(blocks):
    titles = ("", "", "")
    sections = []
    for page, text, level in blocks:
        if level:
            titles = titles[:level - 1] + (text,) + ("",) * (3 - level)
            kind = "exercise" if level == 3 and _EXERCISE.match(text) else "theory"
            sections.append(_Section(titles, "#" * level + " " + text, kind))
        elif sections:
            sections[-1].paras.append((page, text))
        # shortcut: text before the first heading is dropped; fine for SGK pages, revisit for other sources.
    return [s for s in sections if s.paras]


def _split(sec, path, count, max_tokens):
    """Cut a section at paragraph breaks into pieces of at most max_tokens; a single paragraph over the limit stays whole."""
    pieces, cur = [], []
    for para in _labelled_blocks(sec.paras):
        if cur and count(_text(path, [t for _, t in cur + [para]])) > max_tokens:
            pieces.append(_Piece(sec, path, cur[0][0], [t for _, t in cur]))
            cur = []
        cur.append(para)
    if cur:
        pieces.append(_Piece(sec, path, cur[0][0], [t for _, t in cur]))
    return pieces


def _labelled_blocks(paras):
    """Join each labelled paragraph with the unlabelled ones after it, so the block is cut as one paragraph."""
    out, in_block = [], False
    for page, text in paras:
        label = bool(_LABEL.match(text))
        if in_block and not label:
            out[-1] = (out[-1][0], out[-1][1] + "\n\n" + text)
        else:
            out.append((page, text))
        in_block = in_block or label
    return out


def _merge_small(pieces, count, min_tokens, max_tokens):
    """Merge pieces under min_tokens into the previous piece of the same lesson, else the next of the same chapter;
    never across kinds, never past max_tokens."""
    i = 0
    while i < len(pieces):
        if count(pieces[i].text) >= min_tokens or not _merge_into_neighbour(pieces, i, count, max_tokens):
            i += 1


def _merge_into_neighbour(pieces, i, count, max_tokens):
    """-> True when pieces[i] was merged away (the list is one shorter)."""
    p = pieces[i]
    prev = pieces[i - 1] if i > 0 else None
    nxt = pieces[i + 1] if i + 1 < len(pieces) else None
    if prev and prev.same_kind_and_titles(p, depth=2) and _fits(prev, p.paragraphs_for(prev), count, max_tokens):
        prev.body += p.paragraphs_for(prev)
    elif nxt and nxt.same_kind_and_titles(p, depth=1) and _fits(nxt, p.paragraphs_for(nxt), count, max_tokens):
        nxt.body = p.paragraphs_for(nxt) + nxt.body
        nxt.page = p.page
    else:
        return False
    del pieces[i]
    return True


def _fits(into, extra, count, max_tokens):
    return count(_text(into.path, into.body + extra)) <= max_tokens
