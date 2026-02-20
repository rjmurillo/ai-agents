"""Integration tests for LLM fallback in actionability scoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from scripts.llm_classification.classifier import (
    LLMClassificationResult,
    LLMClassifier,
)
from scripts.llm_classification.config import LLMFallbackConfig
from scripts.update_reviewer_signal_stats import (
    CommentData,
    get_actionability_score,
)


def _make_comment(
    body: str,
    created_at: str | None = None,
    is_resolved: bool = False,
    thread_comments: list[dict[str, str]] | None = None,
) -> CommentData:
    """Build a CommentData for testing."""
    if created_at is None:
        created_at = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    return CommentData(
        pr_number=1,
        body=body,
        created_at=created_at,
        path="file.py",
        is_resolved=is_resolved,
        is_outdated=False,
        thread_comments=thread_comments or [],
    )


class TestActionabilityScoreWithLLMFallback:
    """Tests for get_actionability_score with LLM fallback."""

    @pytest.fixture()
    def mock_classifier(self) -> LLMClassifier:
        config = LLMFallbackConfig(enabled=True)
        classifier = LLMClassifier(config=config)
        classifier.classify = MagicMock()  # type: ignore[method-assign]
        classifier.should_use_fallback = MagicMock(return_value=True)  # type: ignore[method-assign]
        return classifier

    def test_no_llm_when_classifier_none(self) -> None:
        comment = _make_comment("neutral comment")
        result = get_actionability_score(comment, llm_classifier=None)

        assert result.used_llm_fallback is False
        assert "LLMFallback" not in result.reasons

    def test_no_llm_when_high_confidence(self) -> None:
        comment = _make_comment("Critical security vulnerability CWE-22")
        config = LLMFallbackConfig(enabled=True)
        classifier = LLMClassifier(config=config)
        classifier.classify = MagicMock()  # type: ignore[method-assign]

        result = get_actionability_score(comment, llm_classifier=classifier)

        classifier.classify.assert_not_called()
        assert result.used_llm_fallback is False

    def test_llm_called_for_low_confidence(
        self, mock_classifier: LLMClassifier
    ) -> None:
        mock_classifier.classify.return_value = LLMClassificationResult(  # type: ignore[attr-defined]
            is_actionable=True,
            confidence=0.85,
            reason="Bug detected",
        )

        comment = _make_comment("This might be an issue")
        result = get_actionability_score(comment, llm_classifier=mock_classifier)

        mock_classifier.classify.assert_called_once()  # type: ignore[attr-defined]
        assert result.used_llm_fallback is True
        assert "LLMFallback" in result.reasons

    def test_llm_result_overrides_heuristic(
        self, mock_classifier: LLMClassifier
    ) -> None:
        mock_classifier.classify.return_value = LLMClassificationResult(  # type: ignore[attr-defined]
            is_actionable=False,
            confidence=0.9,
            reason="Not a real issue",
        )

        comment = _make_comment("This might be an issue")
        result = get_actionability_score(comment, llm_classifier=mock_classifier)

        assert result.is_actionable is False
        assert result.score == 0.1

    def test_llm_actionable_result(self, mock_classifier: LLMClassifier) -> None:
        mock_classifier.classify.return_value = LLMClassificationResult(  # type: ignore[attr-defined]
            is_actionable=True,
            confidence=0.85,
            reason="Security issue",
        )

        comment = _make_comment("This might be an issue")
        result = get_actionability_score(comment, llm_classifier=mock_classifier)

        assert result.is_actionable is True
        assert result.score == 0.9

    def test_llm_low_confidence_uses_heuristic(
        self, mock_classifier: LLMClassifier
    ) -> None:
        mock_classifier.classify.return_value = LLMClassificationResult(  # type: ignore[attr-defined]
            is_actionable=True,
            confidence=0.5,  # Below 0.7 threshold
            reason="Unsure",
        )

        comment = _make_comment("This might be an issue")
        result = get_actionability_score(comment, llm_classifier=mock_classifier)

        # LLM was called but confidence too low, uses heuristic score
        assert result.used_llm_fallback is True
        assert 0.4 <= result.score <= 0.6  # Heuristic range

    def test_llm_cached_result_marked(self, mock_classifier: LLMClassifier) -> None:
        mock_classifier.classify.return_value = LLMClassificationResult(  # type: ignore[attr-defined]
            is_actionable=True,
            confidence=0.9,
            reason="Cached",
            from_cache=True,
        )

        comment = _make_comment("This might be an issue")
        result = get_actionability_score(comment, llm_classifier=mock_classifier)

        assert "LLMCached" in result.reasons

    def test_llm_failure_falls_back_to_heuristic(
        self, mock_classifier: LLMClassifier
    ) -> None:
        mock_classifier.classify.return_value = None  # type: ignore[attr-defined]

        comment = _make_comment("This might be an issue")
        result = get_actionability_score(comment, llm_classifier=mock_classifier)

        assert result.used_llm_fallback is False
        assert "LLMFallback" not in result.reasons


class TestActionabilityResultUsedLLMField:
    """Tests for used_llm_fallback field."""

    def test_default_false(self) -> None:
        comment = _make_comment("test")
        result = get_actionability_score(comment)
        assert result.used_llm_fallback is False

    def test_true_when_llm_used(self) -> None:
        config = LLMFallbackConfig(enabled=True)
        classifier = LLMClassifier(config=config)
        classifier.should_use_fallback = MagicMock(return_value=True)  # type: ignore[method-assign]
        classifier.classify = MagicMock(  # type: ignore[method-assign]
            return_value=LLMClassificationResult(
                is_actionable=True,
                confidence=0.9,
                reason="Test",
            )
        )

        comment = _make_comment("test")
        result = get_actionability_score(comment, llm_classifier=classifier)
        assert result.used_llm_fallback is True
