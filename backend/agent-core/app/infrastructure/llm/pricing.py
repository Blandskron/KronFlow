"""Versioned LLM token pricing table for cost estimation (FK-26)."""

from decimal import Decimal


PRICING_VERSION = "2026-11-v1"
_QUANT = Decimal("0.000001")
_MILLION = Decimal("1000000")

# (input_usd_per_1m_tokens, output_usd_per_1m_tokens)
MODEL_RATES_PER_1M_USD: dict[str, tuple[Decimal, Decimal]] = {
    "openai/gpt-oss-20b": (Decimal("0.10"), Decimal("0.50")),
    "llama-3.3-70b-versatile": (Decimal("0.59"), Decimal("0.79")),
    "llama-3.1-8b-instant": (Decimal("0.05"), Decimal("0.08")),
}


def estimate_cost_usd(
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> tuple[Decimal, str]:
    """Return (estimated_cost_usd, pricing_version_or_unknown) rounded to 6 decimals."""
    if prompt_tokens is None or completion_tokens is None or prompt_tokens < 0 or completion_tokens < 0:
        return Decimal("0.000000"), "unknown"
    rates = MODEL_RATES_PER_1M_USD.get(model.strip())
    if rates is None:
        return Decimal("0.000000"), "unknown"
    in_rate, out_rate = rates
    total = ((Decimal(prompt_tokens) * in_rate) + (Decimal(completion_tokens) * out_rate)) / _MILLION
    return total.quantize(_QUANT), PRICING_VERSION
