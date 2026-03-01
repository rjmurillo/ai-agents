"""Tests for LLM fallback configuration."""

from __future__ import annotations

import pytest

from scripts.llm_classification.config import LLMFallbackConfig


class TestLLMFallbackConfig:
    """Tests for LLMFallbackConfig dataclass."""

    def test_default_values(self) -> None:
        config = LLMFallbackConfig()
        assert config.low_confidence_min == 0.4
        assert config.low_confidence_max == 0.6
        assert config.model == "claude-haiku-4-5-20251001"
        assert config.max_tokens == 100
        assert config.cache_max_entries == 100
        assert config.enabled is True

    def test_is_low_confidence_in_range(self) -> None:
        config = LLMFallbackConfig()
        assert config.is_low_confidence(0.5) is True
        assert config.is_low_confidence(0.4) is True
        assert config.is_low_confidence(0.6) is True

    def test_is_low_confidence_out_of_range(self) -> None:
        config = LLMFallbackConfig()
        assert config.is_low_confidence(0.39) is False
        assert config.is_low_confidence(0.61) is False
        assert config.is_low_confidence(0.0) is False
        assert config.is_low_confidence(1.0) is False

    def test_custom_range(self) -> None:
        config = LLMFallbackConfig(low_confidence_min=0.3, low_confidence_max=0.7)
        assert config.is_low_confidence(0.35) is True
        assert config.is_low_confidence(0.65) is True
        assert config.is_low_confidence(0.25) is False
        assert config.is_low_confidence(0.75) is False

    def test_invalid_min_raises(self) -> None:
        with pytest.raises(ValueError, match="low_confidence_min must be between 0 and 1"):
            LLMFallbackConfig(low_confidence_min=-0.1)

    def test_invalid_max_raises(self) -> None:
        with pytest.raises(ValueError, match="low_confidence_max must be between 0 and 1"):
            LLMFallbackConfig(low_confidence_max=1.5)

    def test_min_gte_max_raises(self) -> None:
        with pytest.raises(
            ValueError, match="low_confidence_min must be less than low_confidence_max"
        ):
            LLMFallbackConfig(low_confidence_min=0.6, low_confidence_max=0.4)

    def test_from_env_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("LLM_FALLBACK_ENABLED", raising=False)
        monkeypatch.delenv("LLM_FALLBACK_MIN", raising=False)
        monkeypatch.delenv("LLM_FALLBACK_MAX", raising=False)

        config = LLMFallbackConfig.from_env()
        assert config.enabled is False  # No API key
        assert config.low_confidence_min == 0.4
        assert config.low_confidence_max == 0.6

    def test_from_env_with_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.delenv("LLM_FALLBACK_ENABLED", raising=False)

        config = LLMFallbackConfig.from_env()
        assert config.enabled is True

    def test_from_env_explicit_disable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("LLM_FALLBACK_ENABLED", "false")

        config = LLMFallbackConfig.from_env()
        assert config.enabled is False

    def test_from_env_custom_thresholds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_FALLBACK_MIN", "0.35")
        monkeypatch.setenv("LLM_FALLBACK_MAX", "0.65")
        monkeypatch.setenv("LLM_FALLBACK_ENABLED", "true")

        config = LLMFallbackConfig.from_env()
        assert config.low_confidence_min == 0.35
        assert config.low_confidence_max == 0.65
