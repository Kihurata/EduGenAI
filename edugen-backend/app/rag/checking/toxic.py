"""Tóm tắt: guardrail T-038: câu có từ cấm (danh sách từ, khớp nguyên từ, không phân biệt hoa thường) bị loại với lỗi toxic_content."""

import re

# shortcut: a short hand-made list; grow it from the toxic_content rejections in the logs.
BANNED = ("đồ ngu", "thằng ngu", "con ngu", "đồ khốn", "khốn nạn", "đm", "địt", "đụ", "lồn", "cặc", "đéo",
          "fuck", "shit", "bitch")
_BANNED = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, BANNED)) + r")(?!\w)", re.IGNORECASE)


def check_toxic(question, retrieved_ids):
    texts = [question.get("stem"), question.get("explanation"), question.get("answer"),
             *(question.get("options") or {}).values(),
             *(s.get("text") for s in question.get("statements") or [] if isinstance(s, dict))]
    found = sorted({m.group(0).lower() for t in texts if isinstance(t, str) for m in _BANNED.finditer(t)})
    return [f"toxic_content: {', '.join(found)}"] if found else []
