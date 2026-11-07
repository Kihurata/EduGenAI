"""Tóm tắt: đọc đề GV tải lên thành bản nháp JSON (T-050), LLM giả. File JSON đúng schema thì dùng luôn, không gọi
LLM; PDF/DOCX thì lấy chữ rồi nhờ LLM tách câu, prompt có danh sách mã chủ đề của môn để LLM chỉ chọn trong đó.
LLM trả không phải JSON, hoặc file không đọc được chữ → ExtractionError có thông báo tiếng Việt.
"""

import json

import pytest

from app.services.draft_extractor import ExtractionError, LLMDraftExtractor

DRAFT = {"exam": "Đề thi thử", "ma_de": "1", "questions": [{"part": "I", "cau": 1, "stem": "x"}]}


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def complete(self, system, prompt, schema):
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        return self.reply


def extractor(reply="", text="Câu 1. Nhiệt độ sôi của nước?"):
    llm = FakeLLM(reply)
    return LLMDraftExtractor(llm, read_text=lambda data, filename: text), llm


def test_json_upload_is_used_as_is_without_llm():
    ex, llm = extractor()
    assert ex.extract(json.dumps(DRAFT).encode(), "de.json", "ly", 12) == DRAFT
    assert llm.calls == []


def test_pdf_text_is_split_by_the_llm_with_the_subject_topic_list():
    ex, llm = extractor(json.dumps(DRAFT))
    assert ex.extract(b"%PDF", "de.pdf", "ly", 12) == DRAFT
    [call] = llm.calls
    assert "Câu 1. Nhiệt độ sôi của nước?" in call["prompt"]
    assert "ly/vat_li_nhiet" in call["prompt"] and "hoa/ester_lipid" not in call["prompt"]
    assert "Vật lí" in call["system"]
    assert call["schema"]["properties"]["questions"]["type"] == "array"


def test_llm_reply_that_is_not_json_is_an_extraction_error():
    ex, _ = extractor("xin lỗi, tôi không đọc được")
    with pytest.raises(ExtractionError, match="LLM"):
        ex.extract(b"%PDF", "de.pdf", "ly", 12)


def test_file_without_text_is_an_extraction_error():
    ex, llm = extractor(json.dumps(DRAFT), text="   ")
    with pytest.raises(ExtractionError, match="chữ"):
        ex.extract(b"%PDF", "de.pdf", "hoa", 12)
    assert llm.calls == []


def test_broken_json_upload_is_an_extraction_error():
    ex, _ = extractor()
    with pytest.raises(ExtractionError, match="JSON"):
        ex.extract(b"{khong phai json", "de.json", "ly", 12)


def test_corrupt_pdf_gives_clear_error_and_temp_dir_is_removed(monkeypatch):
    import tempfile
    from pathlib import Path

    from app.services.draft_extractor import read_text

    seen = []
    real = tempfile.TemporaryDirectory

    class Spy(real):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            seen.append(self.name)

    monkeypatch.setattr(tempfile, "TemporaryDirectory", Spy)
    with pytest.raises(ExtractionError, match="file có thể bị hỏng"):
        read_text(b"day khong phai pdf", "de.pdf")
    assert seen and not Path(seen[0]).exists()


def test_corrupt_docx_gives_clear_error(monkeypatch):
    from app.services.draft_extractor import read_text

    with pytest.raises(ExtractionError, match="file có thể bị hỏng"):
        read_text(b"day khong phai docx", "de.docx")


def test_parse_pdf_releases_the_file_when_it_fails(tmp_path):
    from app.rag.parse import parse_pdf

    pdf = tmp_path / "scan.pdf"
    import pymupdf

    doc = pymupdf.open()
    doc.new_page()  # blank page: no text and no transcribe -> ValueError
    doc.save(pdf)
    doc.close()
    with pytest.raises(ValueError):
        parse_pdf(pdf)
    pdf.unlink()  # PermissionError on Windows if the document was left open


def test_scanned_pdf_is_reported_as_scan_not_corrupt():
    import pymupdf

    from app.services.draft_extractor import read_text

    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    with pytest.raises(ExtractionError, match="ảnh scan"):
        read_text(data, "de.pdf")
