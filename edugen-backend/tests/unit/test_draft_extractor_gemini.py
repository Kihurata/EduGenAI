"""Tóm tắt: đọc đề GV tải lên bằng Gemini, gửi thẳng file như ma trận (T-055, TC-025, TC-026; D-016 sửa đổi 2026-11-07).
Không gọi Gemini thật trong test.

Đầu ra mong muốn:
- PDF (kể cả PDF scan không có chữ) và ảnh PNG/JPG gửi thẳng cho Gemini, đúng mime, nhiệt độ 0, trả JSON theo schema.
- DOCX Gemini không nhận, nên vẫn đổi sang chữ bằng Pandoc rồi gửi chữ. JSON dùng luôn, không gọi Gemini.
- Prompt có tên môn và danh sách mã chủ đề của môn đó.
- Bản nháp lỗi kiểm tra thì đọc lại đúng một lần kèm các lỗi; lần sau không ít lỗi hơn thì giữ lần đầu.
- TC-026: Gemini khai file không có đáp án (hoặc không khai) thì xoá mọi đáp án nó tự điền.
- Lỗi API, trả về không phải JSON, loại file lạ → ExtractionError tiếng Việt.
- DRAFT_EXTRACTOR chọn bộ đọc: gemini (mặc định) hoặc text (cách cũ: lấy chữ rồi gọi make_llm).
"""

import copy
import json
from types import SimpleNamespace

import pytest
from google.genai import errors

from app.core.config import Settings
from app.services import draft_extractor
from app.services.draft_extractor import ExtractionError, LLMDraftExtractor

MC = {"part": "I", "cau": 1, "topic": "ly/vat_li_nhiet", "stem": "Nhiệt độ sôi của nước ở 1 atm là",
      "options": {"A": "0 °C", "B": "100 °C", "C": "273 K", "D": "50 °C"}, "answer": "B"}
TF = {"part": "II", "cau": 1, "topic": "ly/khi_li_tuong", "stem": "Một lượng khí lí tưởng.",
      "statements": [{"label": l, "text": f"Ý {l}", "answer": l in "ac"} for l in "abcd"]}
SA = {"part": "III", "cau": 1, "topic": "ly/vat_li_hat_nhan", "stem": "Chu kì bán rã (ngày)?", "answer": "8"}
GOOD = {"exam": "Đề thi thử Vật lí 2026", "ma_de": "101", "grade": 12, "exam_kind": "tot_nghiep",
        "answer_key_in_file": True, "questions": [MC, TF, SA]}  # fmt: skip
BAD = {**GOOD, "questions": [{**MC, "topic": "khong_co"}, TF, SA]}  # 1 lỗi chủ đề


def reply(d):
    return json.dumps(d, ensure_ascii=False)


GOOD_REPLY = reply(GOOD)


class FakeModels:
    def __init__(self, texts=(GOOD_REPLY,), raises=None):
        self.texts, self.raises, self.calls = list(texts), raises, []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise self.raises
        text = self.texts[min(len(self.calls), len(self.texts)) - 1]
        usage = SimpleNamespace(prompt_token_count=5000, candidates_token_count=6000, thoughts_token_count=None)
        return SimpleNamespace(text=text, usage_metadata=usage)


def no_text(data, filename):
    raise AssertionError("PDF/ảnh phải gửi thẳng cho Gemini, không lấy chữ trước")


def gemini(texts=(GOOD_REPLY,), raises=None, read_text=no_text):
    models = FakeModels(texts, raises)
    ex = draft_extractor.GeminiDraftExtractor("gemini-test", client=SimpleNamespace(models=models), read_text=read_text)
    return ex, models


def file_part(call):
    return next(c for c in call["contents"] if getattr(c, "inline_data", None) is not None)


def prompt_of(call):
    return "\n".join(c for c in call["contents"] if isinstance(c, str))


def test_TC_025_pdf_is_sent_as_a_file_with_the_schema():
    ex, models = gemini()
    draft = ex.extract(b"%PDF scan", "de.pdf", "ly", 12)
    assert draft["questions"][0]["answer"] == "B"
    [call] = models.calls
    assert call["model"] == "gemini-test"
    assert call["config"]["temperature"] == 0
    assert call["config"]["response_mime_type"] == "application/json"
    assert call["config"]["response_schema"]["properties"]["questions"]
    part = file_part(call)
    assert (part.inline_data.mime_type, part.inline_data.data) == ("application/pdf", b"%PDF scan")
    assert ex.usage == [{"input_tokens": 5000, "output_tokens": 6000, "thinking_tokens": 0}]


def test_TC_025_scanned_pdf_is_read_not_rejected():
    """Đề chính thức của Bộ là PDF ảnh scan; trước đây read_text báo 'PDF không có chữ'."""
    import pymupdf

    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    ex, models = gemini()
    assert ex.extract(data, "de-scan.pdf", "ly", 12)["questions"]
    assert file_part(models.calls[0]).inline_data.data == data


@pytest.mark.parametrize("name, mime", [("trang1.png", "image/png"), ("trang1.JPG", "image/jpeg"),
                                        ("trang1.jpeg", "image/jpeg")])  # fmt: skip
def test_TC_025_photos_are_sent_with_their_mime_type(name, mime):
    ex, models = gemini()
    ex.extract(b"anh", name, "hoa", 12)
    assert file_part(models.calls[0]).inline_data.mime_type == mime


def test_TC_025_prompt_has_the_subject_and_its_topic_list_only():
    ex, models = gemini()
    ex.extract(b"%PDF", "de.pdf", "ly", 12)
    text = prompt_of(models.calls[0]) + str(models.calls[0]["config"].get("system_instruction", ""))
    assert "Vật lí" in text
    assert "ly/vat_li_nhiet" in text and "hoa/ester_lipid" not in text


def test_TC_025_docx_is_turned_into_text_then_sent():
    ex, models = gemini(read_text=lambda data, filename: "Câu 1. Nhiệt độ sôi của nước?")
    ex.extract(b"PK docx", "de.docx", "ly", 12)
    [call] = models.calls
    assert not any(getattr(c, "inline_data", None) for c in call["contents"])
    assert "Câu 1. Nhiệt độ sôi của nước?" in prompt_of(call)


def test_TC_025_json_upload_is_used_as_is_without_gemini():
    ex, models = gemini()
    assert ex.extract(reply(GOOD).encode(), "de.json", "ly", 12) == GOOD
    assert models.calls == []


def test_TC_025_unknown_file_type_is_an_extraction_error():
    ex, models = gemini()
    with pytest.raises(ExtractionError, match=r"\.txt"):
        ex.extract(b"abc", "de.txt", "ly", 12)
    assert models.calls == []


def test_TC_025_draft_with_issues_is_read_again_once_with_the_issues():
    ex, models = gemini(texts=(reply(BAD), reply(GOOD)))
    assert ex.extract(b"%PDF", "de.pdf", "ly", 12)["questions"][0]["topic"] == "ly/vat_li_nhiet"
    assert len(models.calls) == 2 and len(ex.usage) == 2
    assert "I-1" in prompt_of(models.calls[1])  # chỗ lệch được nói lại cho Gemini


def test_TC_025_a_retry_that_is_no_better_keeps_the_first_draft():
    worse = {**BAD, "questions": [{**MC, "topic": "khong_co"}, {**TF, "statements": []}, SA]}
    ex, models = gemini(texts=(reply(BAD), reply(worse)))
    assert ex.extract(b"%PDF", "de.pdf", "ly", 12)["questions"][1]["statements"]
    assert len(models.calls) == 2


def test_TC_025_a_clean_draft_is_not_read_again():
    ex, models = gemini()
    ex.extract(b"%PDF", "de.pdf", "ly", 12)
    assert len(models.calls) == 1


def test_TC_025_api_error_is_an_extraction_error():
    ex, _ = gemini(raises=errors.APIError(500, {"error": {"message": "boom"}}))
    with pytest.raises(ExtractionError, match="Gemini"):
        ex.extract(b"%PDF", "de.pdf", "ly", 12)


def test_TC_025_network_error_is_an_extraction_error():
    ex, _ = gemini(raises=TimeoutError("quá giờ"))
    with pytest.raises(ExtractionError, match="Gemini"):
        ex.extract(b"%PDF", "de.pdf", "ly", 12)


def test_TC_025_reply_that_is_not_json_is_an_extraction_error():
    ex, _ = gemini(texts=("xin lỗi",))
    with pytest.raises(ExtractionError, match="JSON"):
        ex.extract(b"%PDF", "de.pdf", "ly", 12)


def test_TC_025_draft_extractor_setting_picks_the_reader(monkeypatch):
    assert Settings().draft_extractor == "gemini"
    monkeypatch.setattr(draft_extractor.settings, "draft_extractor", "gemini")
    monkeypatch.setattr(draft_extractor, "GeminiDraftExtractor", lambda model, **kw: ("gemini", model))
    assert draft_extractor.get_draft_extractor()[0] == "gemini"
    monkeypatch.setattr(draft_extractor.settings, "draft_extractor", "text")
    assert isinstance(draft_extractor.get_draft_extractor(), LLMDraftExtractor)


# --- TC-026: Gemini không được tự điền đáp án ----------------------------------------------------------------------

def answers(draft):
    out = []
    for q in draft["questions"]:
        out.append(q.get("answer") or None)
        out += [s.get("answer") for s in q.get("statements") or []]
    return out


def test_TC_026_answers_are_dropped_when_the_file_has_no_answer_key():
    """Spike T-050: đề Lý 2025 không kèm đáp án, Gemini vẫn tự giải và sai 4/28 câu."""
    ex, _ = gemini(texts=(reply({**GOOD, "answer_key_in_file": False}),))
    draft = ex.extract(b"%PDF", "de.pdf", "ly", 12)
    assert set(answers(draft)) == {None}
    assert draft["answers_from_file"] is False


def test_TC_026_answers_are_dropped_when_gemini_does_not_say():
    no_flag = copy.deepcopy(GOOD)
    no_flag.pop("answer_key_in_file")
    ex, _ = gemini(texts=(reply(no_flag),))
    assert set(answers(ex.extract(b"%PDF", "de.pdf", "ly", 12))) == {None}


def test_TC_026_answers_from_the_file_are_kept():
    ex, _ = gemini()
    draft = ex.extract(b"%PDF", "de.pdf", "ly", 12)
    assert answers(draft) == ["B", None, True, False, True, False, "8"]
    assert draft["answers_from_file"] is True


def test_TC_026_schema_makes_gemini_say_whether_the_file_has_answers():
    ex, models = gemini()
    ex.extract(b"%PDF", "de.pdf", "ly", 12)
    schema = models.calls[0]["config"]["response_schema"]
    assert "answer_key_in_file" in schema["required"]
