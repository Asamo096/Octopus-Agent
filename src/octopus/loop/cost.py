"""Cost tracking for API usage per session.

Tracks token usage and calculates costs based on per-model pricing.
Cache read tokens are billed at 10% of the input token price.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Per-1M-token pricing: (input_price, output_price) in USD
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-opus-4-20250514": (15.0, 75.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
    "gpt-4o": (2.50, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "deepseek-chat": (0.14, 0.28),
    "deepseek-reasoner": (0.55, 2.19),
}


@dataclass
class TokenUsage:
    """Token counts for a single API request."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


@dataclass
class ModelUsage:
    """Aggregated usage for a single model."""

    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    request_count: int = 0
    total_cost_usd: float = 0.0


@dataclass
class CostTracker:
    """Tracks API costs across models within a session."""

    model_usage: dict[str, ModelUsage] = field(default_factory=dict)

    def record_usage(self, model: str, usage: TokenUsage) -> None:
        """Accumulate usage and calculate cost for a model."""
        if model not in self.model_usage:
            self.model_usage[model] = ModelUsage(model=model)

        entry = self.model_usage[model]
        entry.usage.input_tokens += usage.input_tokens
        entry.usage.output_tokens += usage.output_tokens
        entry.usage.cache_read_tokens += usage.cache_read_tokens
        entry.usage.cache_creation_tokens += usage.cache_creation_tokens
        entry.request_count += 1
        entry.total_cost_usd += self._calculate_cost(model, usage)

    def _calculate_cost(self, model: str, usage: TokenUsage) -> float:
        """Calculate cost in USD for the given token usage.

        Cache read tokens are billed at 10% of the input token price.
        """
        input_price, output_price = self._get_pricing(model)

        # Standard input/output costs (per-token, pricing is per 1M)
        input_cost = (usage.input_tokens / 1_000_000) * input_price
        output_cost = (usage.output_tokens / 1_000_000) * output_price

        # Cache reads at 10% of input price
        cache_read_cost = (usage.cache_read_tokens / 1_000_000) * input_price * 0.10

        # Cache creation at input price (same rate as regular input)
        cache_creation_cost = (usage.cache_creation_tokens / 1_000_000) * input_price

        return input_cost + output_cost + cache_read_cost + cache_creation_cost

    def _get_pricing(self, model: str) -> tuple[float, float]:
        """Get (input_price, output_price) per 1M tokens for a model.

        Tries exact match first, then falls back to prefix matching
        (e.g. "claude-sonnet-4-20250514-beta" matches "claude-sonnet-4-20250514").
        Returns (0.0, 0.0) if no pricing is found.
        """
        # Exact match
        if model in MODEL_PRICING:
            return MODEL_PRICING[model]

        # Prefix fallback: find the longest matching key prefix
        best_match = ""
        for key in MODEL_PRICING:
            if model.startswith(key) and len(key) > len(best_match):
                best_match = key

        if best_match:
            return MODEL_PRICING[best_match]

        return (0.0, 0.0)

    def get_total_cost(self) -> float:
        """Return total cost across all models in USD."""
        return sum(entry.total_cost_usd for entry in self.model_usage.values())

    def get_model_breakdown(self) -> list[ModelUsage]:
        """Return per-model usage sorted by cost descending."""
        return sorted(
            self.model_usage.values(),
            key=lambda e: e.total_cost_usd,
            reverse=True,
        )

    def get_summary(self) -> str:
        """Return a formatted multi-line summary of costs."""
        lines: list[str] = []
        lines.append(f"Total cost: ${self.get_total_cost():.4f}")
        lines.append("")

        breakdown = self.get_model_breakdown()
        if not breakdown:
            lines.append("No API usage recorded.")
            return "\n".join(lines)

        lines.append("Model breakdown:")
        for entry in breakdown:
            u = entry.usage
            lines.append(
                f"  {entry.model}: ${entry.total_cost_usd:.4f} "
                f"({entry.request_count} requests, "
                f"{u.input_tokens} in / {u.output_tokens} out"
                + (
                    f", {u.cache_read_tokens} cache-read"
                    if u.cache_read_tokens
                    else ""
                )
                + ")"
            )

        return "\n".join(lines)
