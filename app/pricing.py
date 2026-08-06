"""What a model call costs, so the app can show you the bill.

Rates are US dollars per **million** tokens, keyed by model id. Matching is
longest-prefix, so `claude-haiku-4-5-20251001` picks up the `claude-haiku-4-5`
row without needing an entry per dated snapshot.

A model with no matching row costs `None`, not zero -- the usage page then
shows its tokens and calls but leaves the money column blank. That's the
honest answer for a model we don't have a rate for, and it keeps a wrong
number out of a total someone might act on.

Published rates move. `LIFELOG_PRICE_<PROVIDER>` overrides let you correct one
without editing code -- see `_env_override`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Anthropic's own multipliers for the two cache token classes: a cache read is
# a tenth of the input rate, and writing to the 5-minute cache is 1.25x.
CACHE_READ_MULTIPLIER = 0.1
CACHE_WRITE_MULTIPLIER = 1.25


@dataclass(frozen=True)
class Rate:
    input_per_mtok: float
    output_per_mtok: float


# Anthropic rates are first-party API list prices. The others are the
# providers' published rates for their headline models and are best-effort --
# they change without us noticing, so treat them as an estimate and override
# via env if the number matters to you.
RATES: dict[str, Rate] = {
    # Anthropic
    "claude-fable-5": Rate(10.00, 50.00),
    "claude-mythos-5": Rate(10.00, 50.00),
    "claude-opus-5": Rate(5.00, 25.00),
    "claude-opus-4-8": Rate(5.00, 25.00),
    "claude-opus-4-7": Rate(5.00, 25.00),
    "claude-opus-4-6": Rate(5.00, 25.00),
    "claude-opus-4-5": Rate(5.00, 25.00),
    "claude-sonnet-5": Rate(3.00, 15.00),
    "claude-sonnet-4-6": Rate(3.00, 15.00),
    "claude-sonnet-4-5": Rate(3.00, 15.00),
    "claude-haiku-4-5": Rate(1.00, 5.00),
    # OpenAI
    "gpt-4o-mini": Rate(0.15, 0.60),
    "gpt-4o": Rate(2.50, 10.00),
    # Google
    "gemini-2.0-flash": Rate(0.10, 0.40),
    "gemini-2.0-pro": Rate(1.25, 5.00),
    # xAI
    "grok-2-vision-latest": Rate(2.00, 10.00),
    "grok-2-latest": Rate(2.00, 10.00),
    # DeepSeek
    "deepseek-reasoner": Rate(0.55, 2.19),
    "deepseek-chat": Rate(0.27, 1.10),
}


def _env_override(model: str) -> Rate | None:
    """Read a rate from `LIFELOG_PRICE_<MODEL>` -- e.g.

        LIFELOG_PRICE_CLAUDE_OPUS_5=5,25

    Input rate first, output second, dollars per million tokens. A malformed
    value is ignored rather than raising: a typo in an optional override
    shouldn't take down every model call in the app.
    """
    key = "LIFELOG_PRICE_" + model.upper().replace("-", "_").replace(".", "_")
    raw = os.environ.get(key)
    if not raw:
        return None
    try:
        input_rate, output_rate = (float(part) for part in raw.split(",", 1))
    except ValueError:
        return None
    return Rate(input_rate, output_rate)


def rate_for(model: str) -> Rate | None:
    """The rate for `model`, or None if we don't have one.

    Longest prefix wins so a more specific row always beats a shorter one that
    happens to also match.
    """
    model = (model or "").strip()
    if not model:
        return None

    override = _env_override(model)
    if override:
        return override

    if model in RATES:
        return RATES[model]

    matches = [key for key in RATES if model.startswith(key)]
    if not matches:
        return None
    return RATES[max(matches, key=len)]


def cost_usd(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float | None:
    """Dollars for one call, or None when the model has no known rate."""
    rate = rate_for(model)
    if rate is None:
        return None

    per_input = rate.input_per_mtok / 1_000_000
    per_output = rate.output_per_mtok / 1_000_000

    return (
        input_tokens * per_input
        + output_tokens * per_output
        + cache_read_tokens * per_input * CACHE_READ_MULTIPLIER
        + cache_write_tokens * per_input * CACHE_WRITE_MULTIPLIER
    )


def known_models() -> list[dict]:
    """The rate card, for the UI to show what it's charging against."""
    return [
        {"model": model, "input_per_mtok": rate.input_per_mtok, "output_per_mtok": rate.output_per_mtok}
        for model, rate in sorted(RATES.items())
    ]
