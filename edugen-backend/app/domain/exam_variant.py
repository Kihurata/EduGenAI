"""Mã đề: cùng một đề đã duyệt, mỗi mã đề một thứ tự câu và thứ tự phương án khác nhau.

Hàm thuần, không đụng DB: (câu của đề, mã đề) → câu đã xáo. Đề đã duyệt bị khoá sửa nên chỉ cần
seed suy từ (id đề, mã đề) là dựng lại đúng mã đề cũ bất cứ lúc nào, không phải lưu hoán vị.

Xáo gì:
- Thứ tự câu trong từng phần (Phần I → II → III giữ nguyên).
- Thứ tự 4 phương án của câu nhiều lựa chọn; `answer` đổi theo chữ cái mới.
Không xáo ý a–d của câu đúng sai: mức độ từng ý theo ma trận gắn với vị trí ý.

Không xáo khi nội dung dựa vào vị trí, vì xáo sẽ làm đề sai nghĩa:
- Phương án nhắc phương án khác ("Cả A và B", "Không có đáp án nào đúng") hoặc lời giải nhắc chữ cái
  ("Chọn B") → câu đó giữ nguyên thứ tự phương án.
- Đề bài nhắc câu khác ("câu trước", "câu 3") → cả phần chứa câu đó giữ nguyên thứ tự câu.
Nghi ngờ thì giữ nguyên: nhận nhầm chỉ làm mã đề ít khác nhau hơn, không làm đề sai.
"""

import hashlib
import random
import re
from copy import deepcopy

from app.domain.question import OPTION_LETTERS, Question

CODE_PATTERN = re.compile(r"[0-9A-Za-z]{1,8}")

_LETTER = r"\(?[A-D]\)?(?![0-9A-Za-zÀ-ỹ])"
# Phương án nhắc phương án khác: "A và B", "cả A, B", "tất cả các phương án", "không có đáp án nào".
_OPTION_REFERS = re.compile(
    rf"(?i)(?<![0-9A-Za-zÀ-ỹ$\\]){_LETTER}\s*(?:,|và|hoặc|&)\s*{_LETTER}"
    r"|(?:tất cả|cả)\s+(?:các\s+)?(?:phương án|đáp án|ý|ba|bốn|hai)"
    r"|(?:không|chẳng)\s+(?:có\s+)?(?:phương án|đáp án|ý)\s+nào"
    r"|(?:phương án|đáp án)\s+(?:trên|dưới|còn lại)"
)
# Lời giải nhắc chữ cái phương án: "Chọn B", "đáp án A", "phương án C".
_SOLUTION_REFERS = re.compile(rf"(?i)\b(?:chọn|đáp án|phương án|ý|câu trả lời)\s+(?:là\s+)?{_LETTER}")
# Đề bài nhắc câu khác.
_STEM_REFERS = re.compile(r"(?i)\bcâu\s*(?:\d+|trước|sau|trên|dưới|tiếp)|\b(?:ở|như)\s+câu\b|\bbài\s+trước\b")


def is_valid_code(code: str) -> bool:
    return CODE_PATTERN.fullmatch(code) is not None


def variant_seed(exam_id: object, code: str) -> int:
    """Seed cố định theo (đề, mã đề): cùng đề + cùng mã luôn ra cùng thứ tự."""
    return int.from_bytes(hashlib.sha256(f"{exam_id}:{code}".encode()).digest()[:8], "big")


def options_pinned(q: Question) -> bool:
    """Câu nhiều lựa chọn không được xáo phương án (có nhắc chữ cái hoặc phương án khác)."""
    if any(_OPTION_REFERS.search(o) for o in q["options"]):
        return True
    return bool(_SOLUTION_REFERS.search(q.get("solution") or ""))


def _refers_to_other_question(q: Question) -> bool:
    return bool(_STEM_REFERS.search(q.get("stem") or ""))


def _shuffle_options(q: Question, rng: random.Random) -> Question:
    if q["type"] != "multiple_choice" or options_pinned(q):
        return q
    order = list(range(len(q["options"])))
    rng.shuffle(order)
    old = OPTION_LETTERS.index(q["answer"])
    return q | {"options": [q["options"][i] for i in order], "answer": OPTION_LETTERS[order.index(old)]}


def make_variant(questions: list[Question], seed: int) -> list[Question]:
    """Bản xáo của `questions` theo `seed`; không sửa đầu vào. Số câu và nội dung từng câu không đổi."""
    rng = random.Random(seed)
    questions = deepcopy(questions)
    by_type: dict[str, list[Question]] = {}
    for q in questions:
        by_type.setdefault(q["type"], []).append(q)
    out: list[Question] = []
    for qs in by_type.values():  # thứ tự phần do build_blocks sắp, ở đây chỉ xáo trong phần
        if not any(map(_refers_to_other_question, qs)):
            rng.shuffle(qs)
        out += [_shuffle_options(q, rng) for q in qs]
    return out
