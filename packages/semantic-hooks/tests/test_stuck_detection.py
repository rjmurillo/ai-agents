"""Tests for stuck detection guard."""

import json
import tempfile
from pathlib import Path

import pytest

from semantic_hooks.guards import (
    StuckConfig,
    StuckDetectionGuard,
    StuckResult,
    build_nudge,
    check_stuck,
    extract_topic_signature,
    jaccard_similarity,
    reset_stuck_history,
)


class TestExtractTopicSignature:
    """Tests for extract_topic_signature function."""

    def test_returns_none_for_short_text(self):
        """Should return None for text shorter than 50 chars."""
        assert extract_topic_signature("hello world") is None
        assert extract_topic_signature("a" * 49) is None

    def test_returns_none_for_empty_text(self):
        """Should return None for empty or None input."""
        assert extract_topic_signature("") is None
        assert extract_topic_signature(None) is None

    def test_extracts_significant_words(self):
        """Should extract top words excluding stop words."""
        text = """
        The semantic hooks module provides configuration for Claude Code
        integration. Configuration includes embeddings, thresholds, and
        semantic tension tracking. The embeddings are generated using
        OpenAI's text-embedding model for semantic similarity.
        """
        sig = extract_topic_signature(text)
        assert sig is not None
        words = sig.split(",")
        assert len(words) <= 5
        # Should contain significant words, not stop words
        assert "the" not in words
        assert "and" not in words

    def test_signature_is_sorted_alphabetically(self):
        """Signature words should be sorted for consistent comparison."""
        text = """
        Python programming language features include decorators, generators,
        context managers, and comprehensions. Programming with Python provides
        excellent readability and maintainability for developers.
        """
        sig = extract_topic_signature(text)
        if sig:
            words = sig.split(",")
            assert words == sorted(words)

    def test_returns_none_for_insufficient_words(self):
        """Should return None if fewer than min_words significant words."""
        # Text with mostly stop words
        text = "a" * 50 + " the and but or if then when where what"
        assert extract_topic_signature(text, min_words=2) is None


class TestJaccardSimilarity:
    """Tests for jaccard_similarity function."""

    def test_identical_signatures(self):
        """Identical signatures should have similarity of 1.0."""
        sig = "apple,banana,cherry"
        assert jaccard_similarity(sig, sig) == 1.0

    def test_completely_different_signatures(self):
        """No overlap should give similarity of 0.0."""
        sig1 = "apple,banana,cherry"
        sig2 = "dog,elephant,frog"
        assert jaccard_similarity(sig1, sig2) == 0.0

    def test_partial_overlap(self):
        """Partial overlap should give expected Jaccard coefficient."""
        sig1 = "apple,banana,cherry"
        sig2 = "apple,banana,date"
        # Intersection: {apple, banana} = 2
        # Union: {apple, banana, cherry, date} = 4
        # Jaccard = 2/4 = 0.5
        assert jaccard_similarity(sig1, sig2) == 0.5

    def test_empty_signatures(self):
        """Empty signatures should handle gracefully."""
        # Empty string split gives [""] which is a set with one element
        # Two identical sets have similarity 1.0
        assert jaccard_similarity("", "") == 1.0


class TestCheckStuck:
    """Tests for check_stuck function."""

    @pytest.fixture
    def temp_history_path(self):
        """Create a temporary history file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "stuck-history.json"

    def test_not_stuck_on_first_entry(self, temp_history_path):
        """Should not be stuck on first text."""
        text = """
        The semantic hooks module provides configuration for embeddings
        and semantic tension tracking with OpenAI integration features.
        """
        result = check_stuck(text, temp_history_path)
        assert result.stuck is False
        assert result.signature is not None

    def test_not_stuck_with_different_topics(self, temp_history_path):
        """Should not be stuck when topics are different."""
        texts = [
            """
            The semantic hooks module provides configuration for embeddings
            and semantic tension tracking with OpenAI integration features.
            """,
            """
            Python programming includes decorators, generators, and context
            managers for building maintainable applications with clean code.
            """,
            """
            Database design involves normalization, indexing strategies, and
            query optimization for performance in production systems.
            """,
        ]
        for text in texts:
            result = check_stuck(text, temp_history_path)
        assert result.stuck is False

    def test_stuck_with_repeated_topics(self, temp_history_path):
        """Should detect stuck when same topics repeated."""
        config = StuckConfig(
            history_path=temp_history_path,
            stuck_threshold=3,
            similarity_threshold=0.6,
        )
        # Repeat very similar text 3+ times
        text = """
        The semantic hooks module provides configuration for embeddings
        and semantic tension tracking with OpenAI integration features.
        """
        for _ in range(3):
            result = check_stuck(text, temp_history_path, config)
        assert result.stuck is True
        assert result.nudge is not None
        assert "SELF-REFLECTION" in result.nudge

    def test_history_persists(self, temp_history_path):
        """History should be written to file."""
        text = """
        The semantic hooks module provides configuration for embeddings
        and semantic tension tracking with OpenAI integration features.
        """
        check_stuck(text, temp_history_path)
        assert temp_history_path.exists()
        history = json.loads(temp_history_path.read_text())
        assert len(history) == 1
        assert "signature" in history[0]


class TestBuildNudge:
    """Tests for build_nudge function."""

    def test_contains_repeating_words(self):
        """Nudge should include the repeating words."""
        nudge = build_nudge("semantic,hooks,configuration")
        assert "semantic" in nudge
        assert "hooks" in nudge
        assert "configuration" in nudge

    def test_contains_user_name(self):
        """Nudge should include the user name."""
        nudge = build_nudge("topic,words", user_name="Richard")
        assert "Richard" in nudge

    def test_contains_self_reflection_marker(self):
        """Nudge should have the stuck-detection XML tags."""
        nudge = build_nudge("topic,words")
        assert "<stuck-detection>" in nudge
        assert "</stuck-detection>" in nudge
        assert "SELF-REFLECTION" in nudge


class TestResetStuckHistory:
    """Tests for reset_stuck_history function."""

    def test_resets_history(self):
        """Should clear the history file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "stuck-history.json"
            # Write some history
            path.write_text(json.dumps([{"signature": "test", "timestamp": "now"}]))
            assert reset_stuck_history(path) is True
            history = json.loads(path.read_text())
            assert history == []


class TestStuckDetectionGuard:
    """Tests for StuckDetectionGuard class."""

    @pytest.fixture
    def temp_config(self):
        """Create a config with temporary history path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield StuckConfig(history_path=Path(tmpdir) / "stuck-history.json")

    def test_check_returns_hook_result(self, temp_config):
        """Check should return a HookResult."""
        from semantic_hooks.core import HookContext, HookEvent

        guard = StuckDetectionGuard(config=temp_config)
        context = HookContext(
            event=HookEvent.POST_TOOL_USE,
            tool_result="""
            The semantic hooks module provides configuration for embeddings
            and semantic tension tracking with OpenAI integration features.
            """,
        )
        result = guard.check(context)
        assert result.allow is True

    def test_detects_stuck_loop(self, temp_config):
        """Should detect and report stuck loops."""
        from semantic_hooks.core import HookContext, HookEvent

        guard = StuckDetectionGuard(config=temp_config)
        text = """
        The semantic hooks module provides configuration for embeddings
        and semantic tension tracking with OpenAI integration features.
        """
        for _ in range(3):
            context = HookContext(
                event=HookEvent.POST_TOOL_USE,
                tool_result=text,
            )
            result = guard.check(context)

        assert result.message is not None
        assert "Stuck loop" in result.message
        assert result.additional_context is not None

    def test_reset_clears_history(self, temp_config):
        """Reset should clear the history."""
        guard = StuckDetectionGuard(config=temp_config)
        # Add some history
        from semantic_hooks.core import HookContext, HookEvent

        context = HookContext(
            event=HookEvent.POST_TOOL_USE,
            tool_result="""
            The semantic hooks module provides configuration for embeddings
            and semantic tension tracking with OpenAI integration features.
            """,
        )
        guard.check(context)
        assert guard.reset() is True
        history = json.loads(temp_config.history_path.read_text())
        assert history == []
