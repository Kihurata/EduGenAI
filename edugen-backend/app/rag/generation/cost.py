"""Tóm tắt: chi phí AI (T-039): cộng usage mà ClaudeLLM / GeminiLLM / ClaudeCodeLLM đã ghi cho mỗi lần gọi, tính USD theo prices.json (có nguồn và ngày); model chưa có giá thì usd là None."""

import json
from pathlib import Path

PRICES = json.loads((Path(__file__).with_name("prices.json")).read_text(encoding="utf-8"))

# usage key written by llm.py -> token kind in the price table
_KEYS = {"input_tokens": "input", "output_tokens": "output", "cache_read_input_tokens": "cache_read",
         "cache_creation_input_tokens": "cache_write", "thinking_tokens": "thinking"}


def cost(usage: list[dict], model: str, seconds: float) -> dict:
    """-> {model, calls, tokens, usd, seconds} for the LLM calls of one run (one exam)."""
    tokens = {kind: sum(u.get(key) or 0 for u in usage) for key, kind in _KEYS.items()}
    return {"model": model, "calls": len(usage), "tokens": tokens, "usd": _usd(usage, model, tokens),
            "seconds": round(seconds, 2)}


def _usd(usage, model, tokens):
    if usage and all("total_cost_usd" in u for u in usage):  # `claude -p` reports its own cost
        return sum(u["total_cost_usd"] or 0 for u in usage)
    price = PRICES["models"].get(model)
    if price is None:
        return None
    billed = tokens | {"output": tokens["output"] + tokens["thinking"]}  # thinking is billed as output
    return sum(billed[kind] * price[kind] for kind in price) / 1_000_000
