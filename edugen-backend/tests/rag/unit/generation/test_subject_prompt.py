"""Tóm tắt: prompt sinh câu theo môn (T-050). Toán giữ nguyên prompt cũ; Lý và Hóa đổi tên môn và thêm vài quy tắc
riêng (Lý: đơn vị SI, cho sẵn công thức ngoài chương trình; Hóa: kí hiệu hoá học, nguyên tử khối, cách làm tròn).
Luồng sinh câu chọn prompt theo môn của ô ma trận.
"""

import dataclasses

from app.rag.generation.generate import NO_RAG_SYSTEM_PROMPT, SYSTEM_PROMPT, system_prompt
from app.rag.pipeline import generate_for_cell
from tests.rag.fakes import FakeEmbedder, FakeLLM
from tests.rag.support import LLM_OUTPUT, cell, exam_item, memory_client, reply


def test_toan_keeps_the_existing_prompts():
    assert system_prompt("toan") == SYSTEM_PROMPT
    assert system_prompt("toan", rag=False) == NO_RAG_SYSTEM_PROMPT


def test_physics_prompt_names_the_subject_and_adds_its_rules():
    prompt = system_prompt("ly")
    assert "môn Vật lí" in prompt and "môn Toán" not in prompt
    assert "SI" in prompt and "công thức" in prompt
    assert "Chỉ dùng kiến thức trong các đoạn tài liệu" in prompt


def test_chemistry_prompt_without_rag_uses_the_chemistry_curriculum():
    prompt = system_prompt("hoa", rag=False)
    assert "môn Hoá học" in prompt and "chương trình Hoá học THPT 2018" in prompt
    assert "nguyên tử khối" in prompt and "làm tròn" in prompt


def test_pipeline_uses_the_prompt_of_the_cell_subject():
    item = dataclasses.replace(exam_item(1, "ly/vat_li_nhiet"), subject="ly")
    llm = FakeLLM([reply(LLM_OUTPUT["multiple_choice"] | {"source_chunk_ids": ["e1"]})])
    generate_for_cell(memory_client([item]), FakeEmbedder(), cell(subject="ly", topic="ly/vat_li_nhiet"), llm)
    assert llm.calls[0]["system"] == system_prompt("ly")
