"""Configuration for LLM fallback classification."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMFallbackConfig:
    """Configuration for LLM-based actionability classification fallback.

    Attributes:
        low_confidence_min: Lower bound of low-confidence range (inclusive).
        low_confidence_max: Upper bound of low-confidence range (inclusive).
        model: Claude model to use for classification.
        max_tokens: Maximum tokens for LLM response.
        cache_max_entries: Maximum cache entries before eviction.
        enabled: Whether LLM fallback is enabled.
    """

    low_confidence_min: float = 0.4
    low_confidence_max: float = 0.6
    model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 100
    cache_max_entries: int = 100
    enabled: bool = True

    def __post_init__(self) -> None:
        """Validate configuration bounds."""
        if not 0.0 <= self.low_confidence_min <= 1.0:
            raise ValueError("low_confidence_min must be between 0 and 1")
        if not 0.0 <= self.low_confidence_max <= 1.0:
            raise ValueError("low_confidence_max must be between 0 and 1")
        if self.low_confidence_min >= self.low_confidence_max:
            raise ValueError("low_confidence_min must be less than low_confidence_max")

    def is_low_confidence(self, score: float) -> bool:
        """Check if a heuristic score falls in the low-confidence range."""
        return self.low_confidence_min <= score <= self.low_confidence_max

    @classmethod
    def from_env(cls) -> LLMFallbackConfig:
        """Create config from environment variables.

        Environment variables:
            LLM_FALLBACK_ENABLED: "true" or "false" (default: true if API key present)
            LLM_FALLBACK_MIN: Lower bound (default: 0.4)
            LLM_FALLBACK_MAX: Upper bound (default: 0.6)
            LLM_FALLBACK_MODEL: Model name (default: claude-haiku-4-5-20251001)
            LLM_FALLBACK_CACHE_SIZE: Cache size (default: 100)
        """
        has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        enabled_str = os.environ.get("LLM_FALLBACK_ENABLED", "").lower()

        if enabled_str == "false":
            enabled = False
        elif enabled_str == "true":
            enabled = True
        else:
            enabled = has_api_key

        return cls(
            low_confidence_min=float(os.environ.get("LLM_FALLBACK_MIN", "0.4")),
            low_confidence_max=float(os.environ.get("LLM_FALLBACK_MAX", "0.6")),
            model=os.environ.get("LLM_FALLBACK_MODEL", "claude-haiku-4-5-20251001"),
            cache_max_entries=int(os.environ.get("LLM_FALLBACK_CACHE_SIZE", "100")),
            enabled=enabled,
        )
