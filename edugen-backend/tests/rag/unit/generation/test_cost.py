"""Tóm tắt: chi phí AI mỗi đề (T-039): cộng usage mà các lớp LLM đã ghi, tính USD theo bảng giá có ghi nguồn và ngày; model chưa có giá thì usd là None, không đoán."""

import pytest

from app.rag.generation.cost import PRICES, cost

OPUS = "claude-opus-5-5"


def test_price_table_cites_its_source_and_date():
    assert PRICES["source"] and PRICES["date"]
    assert set(PRICES["models"][OPUS]) == {"input", "output", "cache_read", "cache_write"}


def test_claude_usage_is_summed_and_priced():
    usage = [
        {"input_tokens": 1_000_000, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        {"input_tokens": 0, "output_tokens": 100_000, "cache_read_input_tokens": 1_000_000,
         "cache_creation_input_tokens": 0},
    ]

    c = cost(usage, OPUS, seconds=12.345)

    assert c["model"] == OPUS and c["calls"] == 2 and c["seconds"] == 12.35
    assert c["tokens"] == {"input": 1_000_000, "output": 100_000, "cache_read": 1_000_000, "cache_write": 0,
                           "thinking": 0}
    p = PRICES["models"][OPUS]
    assert c["usd"] == pytest.approx(p["input"] + p["output"] / 10 + p["cache_read"])


def test_thinking_tokens_are_billed_as_output():
    p = PRICES["models"][OPUS]

    c = cost([{"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 1_000_000}], OPUS, 1)

    assert c["tokens"]["thinking"] == 1_000_000
    assert c["usd"] == pytest.approx(p["output"])


def test_claude_code_runs_use_the_cost_the_cli_reported():
    c = cost([{"total_cost_usd": 0.25}, {"total_cost_usd": 0.5}], OPUS, 3)

    assert c["usd"] == pytest.approx(0.75) and c["calls"] == 2


def test_gemini_usage_is_priced_with_thinking_as_output():
    p = PRICES["models"]["gemini-3.5-flash-lite"]
    usage = [{"input_tokens": 1_000_000, "output_tokens": 100_000, "thinking_tokens": 100_000}]  # as GeminiLLM records

    c = cost(usage, "gemini-3.5-flash-lite", 1)

    assert c["usd"] == pytest.approx(p["input"] + p["output"] / 5)


def test_gemini_embedding_is_priced_on_input_tokens():
    p = PRICES["models"]["gemini-embedding-001"]

    assert cost([{"input_tokens": 2_000_000}], "gemini-embedding-001", 1)["usd"] == pytest.approx(2 * p["input"])


def test_unpriced_model_has_no_usd():
    assert cost([{"input_tokens": 10, "output_tokens": 5}], "some-new-model", 1)["usd"] is None


def test_no_calls_cost_nothing():
    c = cost([], OPUS, 0)

    assert c["calls"] == 0 and c["usd"] == 0


@pytest.mark.parametrize(("model", "price"), [
    ("gemini-3.1-flash-lite", {"input": 0.25, "output": 1.5, "cache_read": 0.025}),
    ("gemini-3.8-flash", {"input": 0.75, "output": 3.75, "cache_read": 0.075}),  # until 2026-12-31, then x2
])
def test_t039_compared_gemini_models_are_priced(model, price):
    """T-039 model comparison: aistudio.google.com/docs/pricing, paid Standard, read 2026-11-06."""
    assert PRICES["models"][model] == price
