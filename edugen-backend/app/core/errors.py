"""Lỗi dùng chung giữa domain và tầng gọi RAG."""


class LLMError(Exception):
    """RAG/LLM không sinh hoặc không kiểm được câu hỏi (lỗi model, quá tải, timeout...)."""
