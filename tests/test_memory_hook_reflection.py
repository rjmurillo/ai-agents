"""Tests for the session_end_memory hook (reflection)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from memory_enhancement.hooks.session_end_memory import (
    _find_repo_root,
    _format_reflection,
    _generate_reflection,
)


class TestFindRepoRoot:
    """Tests for repository root detection."""

    @pytest.mark.unit
    def test_finds_git_directory(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "deep" / "nested"
        sub.mkdir(parents=True)
        result = _find_repo_root(sub)
        assert result == tmp_path

    @pytest.mark.unit
    def test_returns_none_when_no_git(self, tmp_path: Path):
        result = _find_repo_root(tmp_path)
        assert result is None or (result / ".git").exists()


class TestFormatReflection:
    """Tests for reflection output formatting."""

    @pytest.mark.unit
    def test_format_basic_summary(self):
        scores = {"mem-1": 0.8, "mem-2": 0.6, "mem-3": 0.9}
        stale = ["mem-2"]
        report = MagicMock(
            health_score=0.75,
            recommendations=["Fix 1 broken citation.", "Verify 2 unverified."],
        )
        result = _format_reflection(scores, stale, report)

        assert "<session-reflection>" in result
        assert "</session-reflection>" in result
        assert "3 memories" in result
        assert "75%" in result
        assert "1 need verification" in result
        assert "Fix 1 broken citation." in result

    @pytest.mark.unit
    def test_format_no_stale(self):
        scores = {"mem-1": 0.95}
        report = MagicMock(health_score=0.95, recommendations=[])
        result = _format_reflection(scores, [], report)

        assert "0 need verification" in result

    @pytest.mark.unit
    def test_format_limits_recommendations_to_3(self):
        scores = {"a": 0.5}
        report = MagicMock(
            health_score=0.5,
            recommendations=["r1", "r2", "r3", "r4", "r5"],
        )
        result = _format_reflection(scores, [], report)
        # Should only include first 3
        assert "r4" not in result
        assert "r5" not in result

    @pytest.mark.unit
    def test_format_empty_scores(self):
        report = MagicMock(health_score=1.0, recommendations=[])
        result = _format_reflection({}, [], report)
        assert "0 memories" in result


class TestGenerateReflection:
    """Tests for the reflection generation pipeline."""

    @pytest.mark.unit
    @patch("memory_enhancement.health.generate_health_report")
    @patch("memory_enhancement.health.detect_stale_memories")
    @patch("memory_enhancement.confidence.update_confidence_scores")
    def test_generates_reflection(
        self, mock_scores, mock_stale, mock_report, tmp_path: Path
    ):
        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()
        (memories_dir / "test.md").write_text("# Test (2026-01-01)\n\nContent\n")

        mock_scores.return_value = {"test": 0.8}
        mock_stale.return_value = []
        mock_report.return_value = MagicMock(
            health_score=0.8, recommendations=["Check stale."]
        )

        result = _generate_reflection(memories_dir, tmp_path)
        assert "<session-reflection>" in result
        assert "1 memories" in result

    @pytest.mark.unit
    @patch("memory_enhancement.confidence.update_confidence_scores")
    def test_empty_memories_returns_empty(self, mock_scores, tmp_path: Path):
        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()
        mock_scores.return_value = {}

        result = _generate_reflection(memories_dir, tmp_path)
        assert result == ""
