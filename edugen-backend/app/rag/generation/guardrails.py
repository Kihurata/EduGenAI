"""Tóm tắt: guardrail T-038 trước khi gọi LLM, chỉ dùng regex và danh sách từ: nhận ra mẫu prompt injection quen thuộc trong đoạn truy xuất (suspicious, chỉ ghi log) và che số điện thoại, email, tên có nhãn thành [PHONE], [EMAIL], [NAME]."""

import logging
import re

from app.rag.dto import Chunk

log = logging.getLogger(__name__)

# shortcut: known phrasings only (EN + VI); add a pattern when a new one shows up in the "suspicious" log.
_INJECTION = re.compile("|".join([  # noqa: FLY002 -- one alternative per line reads better
    r"\b(?:ignore|disregard|forget)\b.{0,20}\b(?:previous|prior|above|earlier)\b.{0,20}\b(?:instructions?|rules?|prompts?)\b",
    r"\byou are now\b",
    r"\bsystem prompt\b",
    r"\b(?:bỏ qua|phớt lờ|quên)\s+(?:mọi|tất cả|các|toàn bộ)\s+(?:chỉ dẫn|hướng dẫn|yêu cầu|quy tắc)",
    r"\bbạn (?:bây giờ|từ giờ) là\b",
    r"</?source\b",  # a fake closing tag would let the rest of the chunk pose as rules
]), re.IGNORECASE)


def suspicious(text: str) -> bool:
    return bool(_INJECTION.search(text))


def log_suspicious(chunks: list[Chunk]):
    """Log, don't drop: the chunk still goes inside a <source> tag that the system prompt marks as data."""
    for c in chunks:
        if suspicious(c.text):
            log.warning("suspicious chunk %s (source %s): looks like a prompt injection", c.id, c.source)


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# VN numbers: 0 or +84, then 9–10 digits with optional space, dot or dash; (?!\w) keeps hex chunk ids intact.
_PHONE = re.compile(r"(?<!\w)(?:\+84[\s.-]?|0)\d(?:[\s.-]?\d){8,9}(?!\w)")
# shortcut: a name is only found after a label on the exam header; a name inside the problem stays (it's the question).
_NAME_LABELS = ("họ và tên thí sinh", "họ và tên", "họ tên", "giáo viên ra đề", "giáo viên", "người ra đề", "thí sinh")
_NAME = re.compile(r"((?:" + "|".join(map(re.escape, _NAME_LABELS)) + r")\s*:\s*)[^\n,;:.]+", re.IGNORECASE)


def mask_pii(text: str) -> str:
    """Phones, emails and labelled names -> [PHONE], [EMAIL], [NAME] before text reaches the LLM."""
    return _NAME.sub(r"\1[NAME]", _PHONE.sub("[PHONE]", _EMAIL.sub("[EMAIL]", text)))
