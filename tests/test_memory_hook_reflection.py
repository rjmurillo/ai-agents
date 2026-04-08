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
        """Verify None is returned when no .git exists in any ancestor."""
        with patch.object(Path, "exists", return_value=False):
            result = _find_repo_root(tmp_path)
            assert result is None


class TestFormatReflection:
    """Tests for reflection output formatting."""

    @pytest.mark.unit
    def test_format_basic_summary(self):
        report = MagicMock(
            total_memories=3,
            health_score=0.75,
            stale_memories=["mem-2"],
            recommendations=["Fix 1 broken citation.", "Verify 2 unverified."],
        )
        result = _format_reflection(report)

        assert "<session-reflection>" in result
        assert "</session-reflection>" in result
        assert "3 memories" in result
        assert "75%" in result
        assert "1 need verification" in result
        assert "Fix 1 broken citation." in result

    @pytest.mark.unit
    def test_format_no_stale(self):
        report = MagicMock(
            total_memories=1,
            health_score=0.95,
            stale_memories=[],
            recommendations=[],
        )
        result = _format_reflection(report)

        assert "0 need verification" in result

    @pytest.mark.unit
    def test_format_limits_recommendations_to_3(self):
        report = MagicMock(
            total_memories=1,
            health_score=0.5,
            stale_memories=[],
            recommendations=["r1", "r2", "r3", "r4", "r5"],
        )
        result = _format_reflection(report)
        # Should only include first 3
        assert "r4" not in result
        assert "r5" not in result

    @pytest.mark.unit
    def test_format_empty_scores(self):
        report = MagicMock(
            total_memories=0,
            health_score=1.0,
            stale_memories=[],
            recommendations=[],
        )
        result = _format_reflection(report)
        assert "0 memories" in result


class TestGenerateReflection:
    """Tests for the reflection generation pipeline."""

    @pytest.mark.unit
    @patch("memory_enhancement.hooks.session_end_memory.extract_session_facts")
    @patch("memory_enhancement.reflection.reinforce_memories")
    @patch("memory_enhancement.health.generate_health_report")
    def test_generates_reflection(
        self, mock_report, mock_reinforce, mock_facts, tmp_path: Path
    ):
        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()
        (memories_dir / "test.md").write_text("# Test (2026-01-01)\n\nContent\n")

        mock_reinforce.return_value = None
        mock_facts.return_value = ["test"]
        mock_report.return_value = MagicMock(
            total_memories=1,
            health_score=0.8,
            stale_memories=[],
            recommendations=["Check stale."],
        )

        result = _generate_reflection(memories_dir, tmp_path)
        assert "<session-reflection>" in result
        assert "1 memories" in result

    @pytest.mark.unit
    @patch("memory_enhancement.hooks.session_end_memory.extract_session_facts")
    @patch("memory_enhancement.reflection.reinforce_memories")
    @patch("memory_enhancement.health.generate_health_report")
    def test_empty_memories_returns_empty(
        self, mock_report, mock_reinforce, mock_facts, tmp_path: Path
    ):
        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()
        mock_reinforce.return_value = None
        mock_facts.return_value = []
        mock_report.return_value = MagicMock(total_memories=0)

        result = _generate_reflection(memories_dir, tmp_path)
        assert result == ""
