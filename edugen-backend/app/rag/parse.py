"""Tóm tắt: đọc PDF thành Markdown theo từng trang (T-002). Trang có chữ dùng pymupdf4llm (cỡ chữ → đề mục #/##/###); trang scan không có chữ thì gửi ảnh cho LLM đọc ảnh (Claude Haiku) chép lại thành Markdown + LaTeX."""

import re
from pathlib import Path

import pymupdf
import pymupdf4llm

_BOLD_HEADING = re.compile(r"^(#{1,6}) \*\*(.+?)\*\*\s*$", re.MULTILINE)


class ScannedPDFError(ValueError):
    """A page has no extractable text and no transcribe function was given."""


def parse_pdf(path, transcribe=None):
    """Return [(page_number, markdown)], page numbers 1-based.

    transcribe(png_bytes) -> markdown is called for pages with no extractable text.
    shortcut: text pages with garbled formulas (Symbol/MathType fonts) still take the text path;
    route them to `transcribe` too once real SGK pages show what garbling looks like.
    """
    # open from bytes: a failed pymupdf.open(path) keeps the file handle alive while the traceback exists (WinError 32)
    try:
        data = Path(path).read_bytes()
    except FileNotFoundError as exc:
        raise pymupdf.FileNotFoundError(f"no such file: {path}") from exc  # same type as pymupdf.open(path)
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        pages = []
        for i, page in enumerate(doc):
            if page.get_text().strip():
                md = pymupdf4llm.to_markdown(doc, pages=[i], use_ocr=False, show_progress=False)
                md = _BOLD_HEADING.sub(r"\1 \2", md).strip()
            elif transcribe:
                md = transcribe(page.get_pixmap(dpi=150).tobytes("png"))
            else:
                raise ScannedPDFError(f"page {i + 1} of {path} has no text and no transcribe function was given")
            pages.append((i + 1, md))
        return pages
    finally:
        doc.close()  # Windows cannot delete a file that is still open
