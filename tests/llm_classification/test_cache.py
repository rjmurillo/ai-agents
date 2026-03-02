"""Tests for LLM classification cache."""

from __future__ import annotations

import pytest

from scripts.llm_classification.cache import ClassificationCache
from scripts.llm_classification.classifier import LLMClassificationResult


class TestClassificationCache:
    """Tests for ClassificationCache."""

    @pytest.fixture()
    def cache(self) -> ClassificationCache:
        return ClassificationCache(max_entries=3)

    @pytest.fixture()
    def sample_result(self) -> LLMClassificationResult:
        return LLMClassificationResult(
            is_actionable=True,
            confidence=0.9,
            reason="Security vulnerability",
        )

    def test_get_miss_returns_none(self, cache: ClassificationCache) -> None:
        assert cache.get("unknown comment") is None

    def test_put_and_get(
        self, cache: ClassificationCache, sample_result: LLMClassificationResult
    ) -> None:
        cache.put("test comment", sample_result)
        result = cache.get("test comment")

        assert result is not None
        assert result.is_actionable is True
        assert result.confidence == 0.9

    def test_normalized_matching(
        self, cache: ClassificationCache, sample_result: LLMClassificationResult
    ) -> None:
        cache.put("This is a test   comment", sample_result)
        result = cache.get("this  is  a  test comment")

        assert result is not None

    def test_hash_normalization(
        self, cache: ClassificationCache, sample_result: LLMClassificationResult
    ) -> None:
        cache.put("Fixed in commit abc1234", sample_result)
        result = cache.get("Fixed in commit def5678")

        assert result is not None

    def test_line_number_normalization(
        self, cache: ClassificationCache, sample_result: LLMClassificationResult
    ) -> None:
        cache.put("Issue at line 42", sample_result)
        result = cache.get("Issue at line 99")

        assert result is not None

    def test_pr_number_normalization(
        self, cache: ClassificationCache, sample_result: LLMClassificationResult
    ) -> None:
        cache.put("Related to #123", sample_result)
        result = cache.get("Related to #456")

        assert result is not None

    def test_lru_eviction(
        self, cache: ClassificationCache, sample_result: LLMClassificationResult
    ) -> None:
        cache.put("first", sample_result)
        cache.put("second", sample_result)
        cache.put("third", sample_result)
        cache.put("fourth", sample_result)  # Should evict "first"

        assert cache.get("first") is None
        assert cache.get("second") is not None
        assert cache.get("third") is not None
        assert cache.get("fourth") is not None

    def test_get_moves_to_end(
        self, cache: ClassificationCache, sample_result: LLMClassificationResult
    ) -> None:
        cache.put("first", sample_result)
        cache.put("second", sample_result)
        cache.put("third", sample_result)

        cache.get("first")

        cache.put("fourth", sample_result)

        assert cache.get("first") is not None
        assert cache.get("second") is None

    def test_len(
        self, cache: ClassificationCache, sample_result: LLMClassificationResult
    ) -> None:
        assert len(cache) == 0
        cache.put("first", sample_result)
        assert len(cache) == 1
        cache.put("second", sample_result)
        assert len(cache) == 2

    def test_clear(
        self, cache: ClassificationCache, sample_result: LLMClassificationResult
    ) -> None:
        cache.put("first", sample_result)
        cache.put("second", sample_result)
        cache.clear()
        assert len(cache) == 0
        assert cache.get("first") is None

    def test_update_existing_entry(
        self, cache: ClassificationCache
    ) -> None:
        result1 = LLMClassificationResult(
            is_actionable=True, confidence=0.9, reason="First"
        )
        result2 = LLMClassificationResult(
            is_actionable=False, confidence=0.8, reason="Second"
        )

        cache.put("same comment", result1)
        cache.put("same comment", result2)

        assert len(cache) == 1
        retrieved = cache.get("same comment")
        assert retrieved is not None
        assert retrieved.is_actionable is False
        assert retrieved.reason == "Second"
