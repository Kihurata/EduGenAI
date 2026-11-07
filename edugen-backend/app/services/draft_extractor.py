"""Tóm tắt: đọc đề GV tải lên thành bản nháp JSON theo schema app.rag.chunking.exam (T-050, T-055). File .json dùng luôn.
Mặc định (GeminiDraftExtractor, D-016 sửa đổi 2026-11-07): PDF (kể cả PDF scan) và ảnh gửi thẳng cho Gemini; DOCX đổi
sang chữ bằng Pandoc rồi gửi chữ; bản nháp lỗi thì đọc lại một lần. Đáp án chỉ giữ khi Gemini khai file có đáp án
(TC-026). Cách cũ (LLMDraftExtractor): lấy chữ PDF bằng app.rag.parse rồi một lần gọi make_llm. Prompt chỉ cho chọn mã
chủ đề trong danh sách của môn (D-013). Lỗi nào cũng thành ExtractionError có thông báo tiếng Việt.
"""

import copy
import json
import logging
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from app.core.config import settings
from app.domain.exam_draft import EXAM_KINDS, normalize_draft, validate_exam_draft
from app.domain.topics import topic_grade, topics_for
from app.rag.chunking.markdown import SUBJECT_NAMES
from app.rag.parse import ScannedPDFError

log = logging.getLogger("edugen.draft_extractor")


class ExtractionError(RuntimeError):
    """Không đọc được đề thành bản nháp; thông báo hiện cho GV."""


class DraftExtractor(Protocol):
    def extract(self, data: bytes, filename: str, subject: str, grade: int) -> dict[str, Any]: ...


SYSTEM = """Bạn chép lại đề kiểm tra môn {subject} THPT (định dạng Bộ GD&ĐT, QĐ 764/2024) thành JSON, không thêm, không bớt, không sửa nội dung.
- Phần I: trắc nghiệm 4 phương án A–D, "answer" là chữ cái. Phần II: đúng/sai, đúng 4 ý a–d, mỗi ý "answer" true/false. Phần III: trả lời ngắn, "answer" là một con số, dấu phẩy thập phân (ví dụ "-1,5").
- Công thức viết LaTeX trong $...$; công thức hoá học dạng $\\mathrm{{H_2SO_4}}$, không dùng \\ce.
- Hình vẽ, đồ thị: mô tả ngắn bằng chữ trong "figure". Ngữ liệu dùng chung cho nhiều câu: chép vào đề bài của từng câu.
- "topic": chỉ chọn một mã trong danh sách được cho; không chắc thì để chuỗi rỗng. "level" (Biết / Hiểu / Vận dụng): chỉ ghi khi đề có ghi, không thì để trống.
- Đề không có đáp án cho câu nào thì để "answer" rỗng; giáo viên sẽ điền khi duyệt."""

_QUESTION = {
    "type": "object",
    "properties": {
        "part": {"type": "string", "enum": ["I", "II", "III"]},
        "cau": {"type": "integer"},
        "topic": {"type": "string"},
        "level": {"type": "string"},
        "stem": {"type": "string"},
        "figure": {"type": "string"},
        "options": {"type": "object", "properties": {k: {"type": "string"} for k in "ABCD"}},
        "statements": {
            "type": "array",
            "items": {"type": "object", "properties": {"label": {"type": "string"}, "text": {"type": "string"},
                                                       "answer": {"type": "boolean"}}},
        },
        "answer": {"type": "string"},
    },
    "required": ["part", "cau", "stem"],
}  # fmt: skip
SCHEMA = {
    "type": "object",
    "properties": {
        "exam": {"type": "string"},
        "ma_de": {"type": "string"},
        "exam_kind": {"type": "string", "enum": list(EXAM_KINDS)},
        "questions": {"type": "array", "items": _QUESTION},
    },
    "required": ["exam", "questions"],
}


def read_text(data: bytes, filename: str) -> str:
    """Chữ của file PDF (theo trang) hoặc DOCX (qua Pandoc)."""
    suffix = Path(filename).suffix.lower()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"upload{suffix}"
        path.write_bytes(data)
        try:
            if suffix == ".pdf":
                from app.rag.parse import parse_pdf

                return "\n\n".join(md for _, md in parse_pdf(path))
            if suffix == ".docx":
                import pypandoc

                return pypandoc.convert_file(str(path), "markdown")
        except ScannedPDFError as exc:
            raise ExtractionError("PDF không có chữ, có thể là ảnh scan") from exc
        except Exception as exc:  # broken file: the teacher sees a clear message, the real error goes to the log
            log.warning("không đọc được file %s", suffix, exc_info=True)
            raise ExtractionError("Không đọc được file PDF/DOCX, file có thể bị hỏng") from exc
    raise ExtractionError(f"Chưa đọc được file {suffix}, chỉ nhận PDF, DOCX hoặc JSON")


class LLMDraftExtractor:
    def __init__(self, llm=None, read_text: Callable[[bytes, str], str] = read_text) -> None:
        """llm None: chọn bằng make_llm khi cần lần đầu, để tải file JSON không cần cấu hình LLM."""
        self._llm = llm
        self._read_text = read_text

    def extract(self, data: bytes, filename: str, subject: str, grade: int) -> dict[str, Any]:
        if Path(filename).suffix.lower() == ".json":
            try:
                return json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ExtractionError(f"File JSON không đúng định dạng: {exc}") from exc
        text = self._read_text(data, filename)
        if not text.strip():
            raise ExtractionError("File không có chữ để đọc (có thể là ảnh scan)")
        topics = "\n".join(f"- {t.strand}/{t.code}: {t.name} (lớp {topic_grade(t, grade)})" for t in topics_for(subject))
        prompt = f"Danh sách mã chủ đề (đề lớp {grade}):\n{topics}\n\nĐề cần chép:\n{text}"
        try:
            if self._llm is None:
                from app.rag.generation.llm import make_llm

                self._llm = make_llm()
            reply = self._llm.complete(SYSTEM.format(subject=SUBJECT_NAMES.get(subject, subject)), prompt, SCHEMA)
            draft = json.loads(reply)
        except json.JSONDecodeError as exc:
            raise ExtractionError("LLM trả về không phải JSON, thử tải lại hoặc dùng file JSON") from exc
        except Exception as exc:  # LLM/network errors of any provider
            raise ExtractionError(f"LLM lỗi khi đọc đề: {exc}") from exc
        if not isinstance(draft, dict):
            raise ExtractionError("LLM trả về không phải một đề JSON")
        return draft


def _topic_list(subject: str, grade: int) -> str:
    return "\n".join(f"- {t.strand}/{t.code}: {t.name} (lớp {topic_grade(t, grade)})" for t in topics_for(subject))


_MIME = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
GEMINI_SYSTEM = SYSTEM + """
- "answer_key_in_file": true chỉ khi chính file có đáp án (bảng đáp án, đáp án ghi cạnh câu, lời giải). Không có thì
  false và để mọi đáp án trống; tuyệt đối không tự giải để điền đáp án."""
GEMINI_SCHEMA = copy.deepcopy(SCHEMA)
GEMINI_SCHEMA["properties"]["answer_key_in_file"] = {"type": "boolean"}
GEMINI_SCHEMA["required"] = [*SCHEMA["required"], "answer_key_in_file"]


def drop_unsourced_answers(draft: dict[str, Any]) -> dict[str, Any]:
    """TC-026: file không có đáp án (hoặc Gemini không khai) thì xoá mọi đáp án Gemini điền; GV điền khi duyệt."""
    from_file = draft.pop("answer_key_in_file", None) is True
    draft["answers_from_file"] = from_file
    if from_file:
        return draft
    for q in draft.get("questions") or []:
        if not isinstance(q, dict):
            continue
        if "answer" in q:
            q["answer"] = ""
        for s in q.get("statements") or []:
            if isinstance(s, dict):
                s["answer"] = None
    return draft


def _problems(draft: dict[str, Any], subject: str, grade: int) -> list[str]:
    """Lỗi đáng đọc lại; câu để trống chủ đề và đáp án bị xoá là việc của GV nên không tính (gọi lại cũng không hơn)."""
    d = normalize_draft(draft, subject, grade)
    blank_topic = {f"{q.get('part')}-{q.get('cau')}" for q in d.get("questions") or [] if isinstance(q, dict) and not q.get("topic")}
    out = []
    for issue in validate_exam_draft(d, subject):
        if issue.question in blank_topic and issue.message.startswith("Chưa chọn chủ đề"):
            continue
        if not d["answers_from_file"] and "đáp án" in issue.message.lower():
            continue
        out.append(f"{issue.question}: {issue.message}" if issue.question else issue.message)
    return out


class GeminiDraftExtractor:
    """Gửi thẳng PDF/ảnh đề cho Gemini, nhận bản nháp JSON theo GEMINI_SCHEMA (như GeminiMatrixConverter, D-016)."""

    def __init__(self, model: str, client=None, timeout_seconds: float = 180,
                 read_text: Callable[[bytes, str], str] = read_text) -> None:  # fmt: skip
        if client is None:
            from google import genai

            client = genai.Client(http_options={"timeout": int(timeout_seconds * 1000)})
        self.client, self.model, self._read_text = client, model, read_text
        self.usage: list[dict] = []

    def _ask(self, contents: list, subject: str) -> dict[str, Any]:
        from google.genai import errors

        system = GEMINI_SYSTEM.format(subject=SUBJECT_NAMES.get(subject, subject))
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=contents,
                config={"system_instruction": system, "temperature": 0, "max_output_tokens": 32768,
                        "response_mime_type": "application/json", "response_schema": GEMINI_SCHEMA},
            )  # fmt: skip
        except errors.APIError as exc:
            raise ExtractionError(f"Gemini không đọc được đề: {exc}") from exc
        except Exception as exc:  # timeouts/network errors come from httpx; show one message
            raise ExtractionError(f"Gemini không phản hồi: {type(exc).__name__}") from exc
        u = response.usage_metadata
        if u is not None:
            self.usage.append({"input_tokens": u.prompt_token_count, "output_tokens": u.candidates_token_count,
                               "thinking_tokens": u.thoughts_token_count or 0})  # fmt: skip
        try:
            draft = json.loads(response.text or "")
        except json.JSONDecodeError as exc:
            raise ExtractionError("Gemini trả về không phải JSON, thử tải lại hoặc dùng file JSON") from exc
        if not isinstance(draft, dict):
            raise ExtractionError("Gemini trả về không phải một đề JSON")
        return drop_unsourced_answers(draft)

    def extract(self, data: bytes, filename: str, subject: str, grade: int) -> dict[str, Any]:
        from google.genai import types

        suffix = Path(filename).suffix.lower()
        if suffix == ".json":
            try:
                return json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ExtractionError(f"File JSON không đúng định dạng: {exc}") from exc
        prompt = f"Danh sách mã chủ đề (đề lớp {grade}):\n{_topic_list(subject, grade)}\n\nChép đề trong file."
        if suffix in _MIME:
            source: list = [types.Part.from_bytes(data=data, mime_type=_MIME[suffix])]
        elif suffix == ".docx":  # Gemini không nhận DOCX
            source = []
            prompt = f"{prompt}\n\nĐề cần chép:\n{self._read_text(data, filename)}"
        else:
            raise ExtractionError(f"Chưa đọc được file {suffix}, chỉ nhận PDF, ảnh PNG/JPG, DOCX hoặc JSON")
        first = self._ask([*source, prompt], subject)
        problems = _problems(first, subject, grade)
        if not problems:
            return first
        # Như D-016: lệch thì đọc lại đúng một lần kèm chỗ lệch; lần sau không hơn thì giữ lần đầu, GV sửa khi duyệt.
        hint = "\n".join(f"- {p}" for p in problems)
        retry = self._ask([*source, f"{prompt}\nLần đọc trước có lỗi, hãy đọc lại thật kỹ:\n{hint}"], subject)
        return retry if len(_problems(retry, subject, grade)) < len(problems) else first


def get_draft_extractor() -> DraftExtractor:
    """Dependency cho FastAPI. DRAFT_EXTRACTOR=gemini (mặc định) gửi thẳng file; text lấy chữ rồi gọi make_llm."""
    if settings.draft_extractor == "gemini":
        return GeminiDraftExtractor(settings.draft_gemini_model)
    return LLMDraftExtractor()
