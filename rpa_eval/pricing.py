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


def cost_usd(model: str, usage: dict | None) -> float | None:
    """Estimated USD for one usage record. 0 if no tokens were used, None if the model has no known price."""
    ti = (usage or {}).get("input_tokens", 0)
    to = (usage or {}).get("output_tokens", 0)
    if not ti and not to:
        return 0.0
    if model not in PRICES_PER_MTOK:
        return None
    pi, po = PRICES_PER_MTOK[model]
    return (ti * pi + to * po) / 1_000_000
