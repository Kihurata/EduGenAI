"""Tóm tắt: lớp gọi LLM thật cho bộ sinh câu (T-010), cùng giao diện complete(system, prompt, schema) với FakeLLM. ClaudeLLM gọi Claude API (structured outputs, cache system prompt, fallback khi bị từ chối); ClaudeCodeLLM gọi `claude -p` bằng tài khoản Claude Code để thử khi chưa có API key; GeminiLLM gọi Gemini API (JSON theo schema, model đổi bằng GEMINI_MODEL) cho spike T-036. Mọi lỗi khi gọi (lỗi API, quá thời gian) đều thành LLMError để Backend chỉ phải bắt một loại lỗi (T-028)."""

import json
import os
import shutil
import subprocess
from typing import Protocol

MODEL = "claude-opus-5-5"
# Free-tier model the T-011 trial ran on; set GEMINI_MODEL for the T-036 runs (Gemini 3.1 Pro).
GEMINI_MODEL = "gemini-3.5-flash-lite"


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    """complete(system, prompt, schema) -> the JSON text of the reply; any failure raises LLMError."""

    def complete(self, system: str, prompt: str, schema: dict) -> str: ...


class ClaudeLLM:
    def __init__(self, client=None, model=MODEL, effort="medium"):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self.client, self.model, self.effort = client, model, effort
        self.usage = []  # one dict per call, for the TC-004 cost report

    def complete(self, system, prompt, schema):
        import anthropic
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                # shortcut: SYSTEM_PROMPT is below the minimum cacheable prefix, so this only pays off
                # once the few-shot block moves into the system prompt; do that if TC-004 cost is high.
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.APIError as e:
            raise LLMError(f"Claude API error: {e}") from e
        u = response.usage
        self.usage.append({k: getattr(u, k) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                                      "cache_creation_input_tokens")})
        if response.stop_reason in ("refusal", "max_tokens"):
            raise LLMError(f"Claude stopped with {response.stop_reason}: {response.stop_details}")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise LLMError("Claude reply has no text block")
        return text


class ClaudeCodeLLM:
    """Runs `claude -p` on the logged-in Claude Code account (Pro plan); for trying T-010 without an API key."""

    def __init__(self, model=MODEL, effort="medium"):
        self.model, self.effort = model, effort
        self.usage = []

    def complete(self, system, prompt, schema):
        cmd = [_claude_exe(), "-p", "--output-format", "json", "--tools", "",
               "--model", self.model, "--effort", self.effort,
               "--system-prompt", system, "--json-schema", json.dumps(schema)]
        try:
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=600,
                                  check=False)  # returncode is reported below
        except subprocess.TimeoutExpired as e:
            raise LLMError(f"claude -p timed out after {e.timeout}s") from e
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise LLMError(f"claude -p failed ({proc.returncode}): {proc.stderr or proc.stdout}") from None
        if out.get("is_error") or out.get("structured_output") is None:
            raise LLMError(f"claude -p error: {out.get('result')}")
        self.usage.append({"total_cost_usd": out.get("total_cost_usd")})
        return json.dumps(out["structured_output"], ensure_ascii=False)


class GeminiLLM:
    """Gemini API with a JSON-schema response; reads GEMINI_API_KEY (or GOOGLE_API_KEY) from the environment."""

    def __init__(self, client=None, model=None):
        if client is None:
            from google import genai
            client = genai.Client()
        self.client = client
        self.model = model or os.environ.get("GEMINI_MODEL", GEMINI_MODEL)
        self.usage = []

    def complete(self, system, prompt, schema):
        from google.genai import errors
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={"system_instruction": system, "response_mime_type": "application/json",
                        "response_json_schema": schema, "max_output_tokens": 32768},
            )
        except errors.APIError as e:
            raise LLMError(f"Gemini API error: {e}") from e
        u = response.usage_metadata
        self.usage.append({"input_tokens": u.prompt_token_count, "output_tokens": u.candidates_token_count,
                           "thinking_tokens": u.thoughts_token_count or 0})
        if not response.candidates:
            raise LLMError(f"Gemini blocked the prompt: {getattr(response, 'prompt_feedback', None)}")
        reason = response.candidates[0].finish_reason
        reason = getattr(reason, "name", reason)
        if reason != "STOP" or not response.text:
            raise LLMError(f"Gemini stopped with {reason}")
        return response.text


def _claude_exe():
    path = shutil.which("claude") or "claude"
    # npm's claude.cmd goes through cmd.exe, which mangles quotes in the JSON arguments; call the exe it wraps.
    exe = os.path.join(os.path.dirname(path), "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe")
    return exe if path.lower().endswith(".cmd") and os.path.exists(exe) else path


def make_llm():
    """LLM_PROVIDER=gemini|claude wins; else ClaudeLLM with ANTHROPIC_API_KEY, GeminiLLM with GEMINI_API_KEY,
    else ClaudeCodeLLM if the `claude` CLI is installed."""
    provider = os.environ.get("LLM_PROVIDER", "").lower()
    if provider == "gemini":
        return GeminiLLM()
    if provider == "claude" or os.environ.get("ANTHROPIC_API_KEY"):
        return ClaudeLLM()
    if os.environ.get("GEMINI_API_KEY"):
        return GeminiLLM()
        return ClaudeLLM()
    if shutil.which("claude"):
        return ClaudeCodeLLM()
    raise LLMError("no ANTHROPIC_API_KEY, no GEMINI_API_KEY and no `claude` CLI on PATH")
