"""Tests for LLM classifier."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scripts.llm_classification.cache import ClassificationCache
from scripts.llm_classification.classifier import (
    LLMClassificationResult,
    LLMClassifier,
)
from scripts.llm_classification.config import LLMFallbackConfig

try:
    import anthropic  # noqa: F401

    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


class TestLLMClassifier:
    """Tests for LLMClassifier."""

    @pytest.fixture()
    def disabled_config(self) -> LLMFallbackConfig:
        return LLMFallbackConfig(enabled=False)

    @pytest.fixture()
    def enabled_config(self) -> LLMFallbackConfig:
        return LLMFallbackConfig(enabled=True)

    @pytest.fixture()
    def cache(self) -> ClassificationCache:
        return ClassificationCache(max_entries=10)

    def test_classify_returns_none_when_disabled(
        self, disabled_config: LLMFallbackConfig
    ) -> None:
        classifier = LLMClassifier(config=disabled_config)
        result = classifier.classify("test comment")
        assert result is None

    def test_should_use_fallback_when_disabled(
        self, disabled_config: LLMFallbackConfig
    ) -> None:
        classifier = LLMClassifier(config=disabled_config)
        assert classifier.should_use_fallback(0.5) is False

    def test_should_use_fallback_in_range(
        self, enabled_config: LLMFallbackConfig
    ) -> None:
        classifier = LLMClassifier(config=enabled_config)
        assert classifier.should_use_fallback(0.5) is True
        assert classifier.should_use_fallback(0.4) is True
        assert classifier.should_use_fallback(0.6) is True

    def test_should_use_fallback_out_of_range(
        self, enabled_config: LLMFallbackConfig
    ) -> None:
        classifier = LLMClassifier(config=enabled_config)
        assert classifier.should_use_fallback(0.39) is False
        assert classifier.should_use_fallback(0.61) is False

    def test_classify_returns_cached_result(
        self,
        enabled_config: LLMFallbackConfig,
        cache: ClassificationCache,
    ) -> None:
        cached_result = LLMClassificationResult(
            is_actionable=True,
            confidence=0.95,
            reason="Cached",
        )
        cache.put("test comment", cached_result)

        classifier = LLMClassifier(config=enabled_config, cache=cache)
        result = classifier.classify("test comment")

        assert result is not None
        assert result.is_actionable is True
        assert result.from_cache is True

    @pytest.mark.skipif(not HAS_ANTHROPIC, reason="anthropic package not installed")
    def test_classify_caches_llm_result(
        self,
        enabled_config: LLMFallbackConfig,
        cache: ClassificationCache,
    ) -> None:
        mock_response = MagicMock()
        llm_json = '{"is_actionable": true, "confidence": 0.9, "reason": "Bug found"}'
        mock_response.content = [MagicMock(text=llm_json)]

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_client.messages.create.return_value = mock_response
                mock_anthropic.return_value = mock_client

                classifier = LLMClassifier(config=enabled_config, cache=cache)
                result = classifier.classify("new comment")

                assert result is not None
                assert result.is_actionable is True
                assert result.from_cache is False
                assert len(cache) == 1

    @pytest.mark.skipif(not HAS_ANTHROPIC, reason="anthropic package not installed")
    def test_classify_returns_none_on_api_error(
        self,
        enabled_config: LLMFallbackConfig,
        cache: ClassificationCache,
    ) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("anthropic.Anthropic") as mock_anthropic:
                mock_client = MagicMock()
                mock_client.messages.create.side_effect = Exception("API error")
                mock_anthropic.return_value = mock_client

                classifier = LLMClassifier(config=enabled_config, cache=cache)
                result = classifier.classify("test comment")

                assert result is None

    def test_config_property(self, enabled_config: LLMFallbackConfig) -> None:
        classifier = LLMClassifier(config=enabled_config)
        assert classifier.config is enabled_config


class TestLLMClassificationResult:
    """Tests for LLMClassificationResult dataclass."""

    def test_default_from_cache(self) -> None:
        result = LLMClassificationResult(
            is_actionable=True,
            confidence=0.8,
            reason="Test",
        )
        assert result.from_cache is False

    def test_frozen(self) -> None:
        result = LLMClassificationResult(
            is_actionable=True,
            confidence=0.8,
            reason="Test",
        )
        with pytest.raises(AttributeError):
            result.is_actionable = False  # type: ignore[misc]
