"""Per-token API prices, used only to estimate spend from stored token usage.

Source: https://platform.claude.com/docs/en/about-claude/pricing
(docs.claude.com redirects there), retrieved 2026-11-03. USD per million tokens, base input / output,
first-party API, global routing, no caching or batch discount (the harness uses neither).

Haiku 5.5 costs more for prompts over 100,000 tokens ($0.50 / $2.50). Usage is stored per trial rather
than per request, so that tier cannot be detected here. The lower tier is assumed.
"""
from __future__ import annotations

PRICES_PER_MTOK = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


def add_usage(total: dict, resp_usage) -> dict:
    """Add one API response's usage to a running total. Cache fields are kept so that no billed token goes uncounted."""
    written = getattr(resp_usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(resp_usage, "cache_read_input_tokens", 0) or 0
    total["input_tokens"] = total.get("input_tokens", 0) + resp_usage.input_tokens
    total["output_tokens"] = total.get("output_tokens", 0) + resp_usage.output_tokens
    total["cache_creation_input_tokens"] = total.get("cache_creation_input_tokens", 0) + written
    total["cache_read_input_tokens"] = total.get("cache_read_input_tokens", 0) + read
    total["max_prompt_tokens"] = max(total.get("max_prompt_tokens", 0), resp_usage.input_tokens + written + read)
    return total


def cost_usd(model: str, usage: dict | None) -> float | None:
    """Estimated USD for one usage record. 0 if no tokens were used, None if the model has no known price."""
    ti = (usage or {}).get("input_tokens", 0)
    to = (usage or {}).get("output_tokens", 0)
    written = (usage or {}).get("cache_creation_input_tokens", 0)
    read = (usage or {}).get("cache_read_input_tokens", 0)
    if not ti and not to and not written and not read:
        return 0.0
    if model not in PRICES_PER_MTOK:
        return None
    pi, po = PRICES_PER_MTOK[model]
    # Standard 5-minute cache rates: writes at 1.25x input, reads at 0.1x. The harness does not ask for caching.
    return ((ti + 1.25 * written + 0.1 * read) * pi + to * po) / 1_000_000
