"""Tóm tắt: unit test lớp gọi LLM (T-010) bằng client giả: ClaudeLLM gửi đúng model/effort/schema/cache/fallback, ghi usage, bị từ chối hoặc hết token thì LLMError; ClaudeCodeLLM đọc kết quả `claude -p`, lỗi và quá giờ thành LLMError; make_llm chọn bản theo API key / CLI (trước đây chưa có test)."""

import json
import subprocess
from types import SimpleNamespace as NS

import pytest

from app.rag.generation import llm as llm_module
from app.rag.generation.llm import MODEL, ClaudeCodeLLM, ClaudeLLM, GeminiLLM, LLMError, make_llm

SCHEMA = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"], "additionalProperties": False}


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _response(text='{"n": 4}', stop_reason="end_turn", content=None):
    usage = NS(input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    content = [NS(type="thinking", thinking=""), NS(type="text", text=text)] if content is None else content
    return NS(content=content, stop_reason=stop_reason, stop_details=None, usage=usage)


def _cli(monkeypatch, stdout, returncode=0, stderr=""):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"], seen["kwargs"] = cmd, kwargs
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return seen


# --- ClaudeLLM -------------------------------------------------------------------------------------------------

def test_request_uses_model_effort_schema_cache_and_fallback():
    client = FakeClient(_response())

    out = ClaudeLLM(client=client).complete("SYS", "PROMPT", schema=SCHEMA)

    assert json.loads(out) == {"n": 4}
    req = client.calls[0]
    assert req["model"] == "claude-opus-5-5"
    assert req["output_config"] == {"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}}
    assert req["system"] == [{"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}]
    assert req["messages"] == [{"role": "user", "content": "PROMPT"}]
    assert req["fallbacks"] == "default" and req["betas"] == ["server-side-fallback-2026-07-01"]


def test_model_and_effort_can_be_changed():
    client = FakeClient(_response())

    ClaudeLLM(client=client, model="claude-sonnet-5-5", effort="low").complete("S", "P", schema=SCHEMA)

    assert client.calls[0]["model"] == "claude-sonnet-5-5"
    assert client.calls[0]["output_config"]["effort"] == "low"


def test_max_tokens_leaves_room_for_a_full_cell():
    client = FakeClient(_response())

    ClaudeLLM(client=client).complete("S", "P", schema=SCHEMA)

    assert client.calls[0]["max_tokens"] >= 8000


def test_usage_is_recorded_for_cost_report():
    llm = ClaudeLLM(client=FakeClient(_response()))
    llm.complete("SYS", "PROMPT", schema=SCHEMA)
    assert llm.usage == [{"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 0,
                          "cache_creation_input_tokens": 0}]


def test_usage_grows_by_one_entry_per_call():
    llm = ClaudeLLM(client=FakeClient(_response()))

    for _ in range(3):
        llm.complete("SYS", "PROMPT", schema=SCHEMA)

    assert len(llm.usage) == 3


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_refusal_or_truncation_raises(stop_reason):
    with pytest.raises(LLMError, match=stop_reason):
        ClaudeLLM(client=FakeClient(_response(stop_reason=stop_reason))).complete("SYS", "PROMPT", schema=SCHEMA)


def test_the_first_text_block_is_returned_after_thinking():
    content = [NS(type="thinking", thinking="..."), NS(type="text", text='{"n": 1}'), NS(type="text", text='{"n": 2}')]

    out = ClaudeLLM(client=FakeClient(_response(content=content))).complete("S", "P", schema=SCHEMA)

    assert out == '{"n": 1}'


def test_a_reply_without_text_becomes_llm_error():
    with pytest.raises(LLMError):
        ClaudeLLM(client=FakeClient(_response(content=[NS(type="thinking", thinking="")]))).complete("S", "P", SCHEMA)


def test_api_error_becomes_llm_error():
    """T-028: the Backend only ever sees LLMError, with the anthropic error kept as the cause."""
    import anthropic
    import httpx

    class FailingClient(FakeClient):
        def _create(self, **kwargs):
            raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))

    with pytest.raises(LLMError) as info:
        ClaudeLLM(client=FailingClient(None)).complete("SYS", "PROMPT", schema=SCHEMA)
    assert isinstance(info.value.__cause__, anthropic.APIConnectionError)


def test_a_failed_call_records_no_usage():
    import anthropic
    import httpx

    class FailingClient(FakeClient):
        def _create(self, **kwargs):
            raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))

    llm = ClaudeLLM(client=FailingClient(None))
    with pytest.raises(LLMError):
        llm.complete("S", "P", schema=SCHEMA)
    assert llm.usage == []


# --- ClaudeCodeLLM ---------------------------------------------------------------------------------------------

def test_claude_code_llm_returns_structured_output(monkeypatch):
    seen = _cli(monkeypatch, json.dumps({"is_error": False, "structured_output": {"n": 4}}))

    out = ClaudeCodeLLM().complete("SYS", "PROMPT", schema=SCHEMA)

    assert json.loads(out) == {"n": 4}
    assert seen["kwargs"]["input"] == "PROMPT"
    cmd = seen["cmd"]
    assert cmd[cmd.index("--system-prompt") + 1] == "SYS"
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == SCHEMA


def test_claude_code_llm_runs_print_mode_without_tools_on_the_chosen_model(monkeypatch):
    seen = _cli(monkeypatch, json.dumps({"is_error": False, "structured_output": {"n": 4}}))

    ClaudeCodeLLM(model="claude-haiku-5-5", effort="low").complete("SYS", "PROMPT", schema=SCHEMA)

    cmd = seen["cmd"]
    assert "-p" in cmd and cmd[cmd.index("--output-format") + 1] == "json"
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == "claude-haiku-5-5" and cmd[cmd.index("--effort") + 1] == "low"
    assert seen["kwargs"]["timeout"] == 600


def test_claude_code_llm_keeps_vietnamese_in_the_reply(monkeypatch):
    _cli(monkeypatch, json.dumps({"is_error": False, "structured_output": {"stem": "Đạo hàm"}}))

    assert "Đạo hàm" in ClaudeCodeLLM().complete("S", "P", schema=SCHEMA)


def test_claude_code_llm_records_cost(monkeypatch):
    _cli(monkeypatch, json.dumps({"is_error": False, "structured_output": {"n": 4}, "total_cost_usd": 0.03}))
    llm = ClaudeCodeLLM()

    llm.complete("S", "P", schema=SCHEMA)

    assert llm.usage == [{"total_cost_usd": 0.03}]


def test_claude_code_llm_error_raises(monkeypatch):
    _cli(monkeypatch, json.dumps({"is_error": True, "result": "rate limited"}), returncode=1)
    with pytest.raises(LLMError, match="rate limited"):
        ClaudeCodeLLM().complete("SYS", "PROMPT", schema=SCHEMA)


def test_claude_code_llm_without_structured_output_raises(monkeypatch):
    _cli(monkeypatch, json.dumps({"is_error": False, "result": "plain text"}))
    with pytest.raises(LLMError, match="plain text"):
        ClaudeCodeLLM().complete("S", "P", schema=SCHEMA)


def test_claude_code_llm_non_json_stdout_raises_with_stderr(monkeypatch):
    _cli(monkeypatch, "", returncode=2, stderr="not logged in")
    with pytest.raises(LLMError, match=r"\(2\).*not logged in"):
        ClaudeCodeLLM().complete("S", "P", schema=SCHEMA)


def test_claude_code_llm_timeout_becomes_llm_error(monkeypatch):
    def timeout(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(LLMError, match="timed out"):
        ClaudeCodeLLM().complete("SYS", "PROMPT", schema=SCHEMA)


# --- make_llm (which LLM the pipeline gets) --------------------------------------------------------------------

def test_api_key_selects_the_claude_api(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    llm = make_llm()

    assert isinstance(llm, ClaudeLLM) and llm.model == MODEL


def test_without_a_key_the_claude_cli_is_used(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm_module.shutil, "which", lambda name: "/usr/bin/claude")

    assert isinstance(make_llm(), ClaudeCodeLLM)


@pytest.mark.parametrize("key", [None, ""])
def test_without_key_or_cli_there_is_a_clear_error(monkeypatch, key):
    if key is None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    else:
        monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    monkeypatch.setattr(llm_module.shutil, "which", lambda name: None)

    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        make_llm()


def test_claude_exe_is_the_cli_path_outside_windows(monkeypatch):
    monkeypatch.setattr(llm_module.shutil, "which", lambda name: "/usr/local/bin/claude")

    assert llm_module._claude_exe() == "/usr/local/bin/claude"


def test_llm_error_is_a_runtime_error():
    assert issubclass(LLMError, RuntimeError)




class FakeGeminiClient:
    def __init__(self, response=None, error=None):
        self.response, self.error = response, error
        self.calls = []
        self.models = NS(generate_content=self._generate)

    def _generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def _gemini_response(text='{"n": 4}', finish_reason="STOP"):
    usage = NS(prompt_token_count=10, candidates_token_count=5, thoughts_token_count=3)
    return NS(text=text, candidates=[NS(finish_reason=NS(name=finish_reason))], usage_metadata=usage)


def test_gemini_request_has_model_system_prompt_and_json_schema():
    client = FakeGeminiClient(_gemini_response())

    out = GeminiLLM(client=client, model="gemini-test").complete("SYS", "PROMPT", schema=SCHEMA)

    assert json.loads(out) == {"n": 4}
    req = client.calls[0]
    assert req["model"] == "gemini-test"
    assert req["contents"] == "PROMPT"
    assert req["config"]["system_instruction"] == "SYS"
    assert req["config"]["response_mime_type"] == "application/json"
    assert req["config"]["response_json_schema"] == SCHEMA


def test_gemini_model_comes_from_env(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-from-env")
    client = FakeGeminiClient(_gemini_response())
    GeminiLLM(client=client).complete("SYS", "PROMPT", schema=SCHEMA)
    assert client.calls[0]["model"] == "gemini-from-env"


def test_gemini_thinks_at_medium_level_by_default():
    """TC-016: without thinking, flash-lite's short answers came from mental arithmetic and SymPy disagreed."""
    client = FakeGeminiClient(_gemini_response())
    GeminiLLM(client=client, model="gemini-test").complete("SYS", "PROMPT", schema=SCHEMA)
    assert client.calls[0]["config"]["thinking_config"] == {"thinking_level": "medium"}


def test_gemini_thinking_level_comes_from_env_and_default_sends_none(monkeypatch):
    monkeypatch.setenv("GEMINI_THINKING", "HIGH")
    client = FakeGeminiClient(_gemini_response())
    GeminiLLM(client=client, model="gemini-test").complete("SYS", "PROMPT", schema=SCHEMA)
    assert client.calls[0]["config"]["thinking_config"] == {"thinking_level": "high"}

    monkeypatch.setenv("GEMINI_THINKING", "default")
    GeminiLLM(client=client, model="gemini-test").complete("SYS", "PROMPT", schema=SCHEMA)
    assert "thinking_config" not in client.calls[1]["config"]


def test_unknown_gemini_thinking_level_fails_at_once(monkeypatch):
    monkeypatch.setenv("GEMINI_THINKING", "max")
    with pytest.raises(LLMError, match="GEMINI_THINKING"):
        GeminiLLM(client=FakeGeminiClient(_gemini_response()), model="gemini-test")


def test_gemini_usage_is_recorded():
    llm = GeminiLLM(client=FakeGeminiClient(_gemini_response()), model="gemini-test")
    llm.complete("SYS", "PROMPT", schema=SCHEMA)
    assert llm.usage == [{"input_tokens": 10, "output_tokens": 5, "thinking_tokens": 3}]


@pytest.mark.parametrize("finish_reason", ["MAX_TOKENS", "SAFETY"])
def test_gemini_blocked_or_truncated_raises(finish_reason):
    client = FakeGeminiClient(_gemini_response(text=None, finish_reason=finish_reason))
    with pytest.raises(LLMError, match=finish_reason):
        GeminiLLM(client=client, model="gemini-test").complete("SYS", "PROMPT", schema=SCHEMA)


def test_gemini_api_error_becomes_llm_error():
    """T-028: the Backend only ever sees LLMError, with the Gemini error kept as the cause."""
    errors = pytest.importorskip("google.genai.errors")
    error = errors.APIError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    with pytest.raises(LLMError) as info:
        GeminiLLM(client=FakeGeminiClient(error=error), model="gemini-test").complete("SYS", "PROMPT", schema=SCHEMA)
    assert info.value.__cause__ is error


def test_make_llm_picks_gemini_when_only_gemini_key_is_set(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.rag.generation.llm.GeminiLLM.__init__", lambda self, **kw: None)
    assert isinstance(make_llm(), GeminiLLM)


def test_make_llm_provider_env_overrides_key_order(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a-key")
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setattr("app.rag.generation.llm.GeminiLLM.__init__", lambda self, **kw: None)
    assert isinstance(make_llm(), GeminiLLM)
