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
    def test_format_singular_decay_verb(self):
        report = MagicMock(
            total_memories=1,
            health_score=0.8,
            stale_memories=[],
            recommendations=[],
        )
        result = _format_reflection(report, session_facts=[], decayed=["mem-1"])
        assert "1 exceeds the age threshold" in result

    @pytest.mark.unit
    def test_format_plural_decay_verb(self):
        report = MagicMock(
            total_memories=3,
            health_score=0.6,
            stale_memories=[],
            recommendations=[],
        )
        result = _format_reflection(report, session_facts=[], decayed=["m1", "m2"])
        assert "2 exceed the age threshold" in result

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


class TestReinforceMemories:
    """Tests for reinforce_memories persistence logic."""

    @pytest.mark.unit
    @patch("memory_enhancement.reflection.save_memory")
    @patch("memory_enhancement.reflection.update_confidence_scores_with_memories")
    def test_saves_when_score_exceeds_epsilon(self, mock_update, mock_save, tmp_path: Path):
        memory = MagicMock()
        memory.memory_id = "mem-1"
        memory.confidence = 0.50

        mock_update.return_value = ({"mem-1": 0.62}, [memory])

        from memory_enhancement.reflection import reinforce_memories

        result = reinforce_memories(tmp_path, tmp_path)

        assert result == {"mem-1": 0.62}
        mock_save.assert_called_once_with(memory, tmp_path)
        assert memory.confidence == 0.62

    @pytest.mark.unit
    @patch("memory_enhancement.reflection.save_memory")
    @patch("memory_enhancement.reflection.update_confidence_scores_with_memories")
    def test_skips_save_when_within_epsilon(self, mock_update, mock_save, tmp_path: Path):
        memory = MagicMock()
        memory.memory_id = "mem-1"
        memory.confidence = 0.50

        mock_update.return_value = ({"mem-1": 0.505}, [memory])

        from memory_enhancement.reflection import reinforce_memories

        reinforce_memories(tmp_path, tmp_path)

        mock_save.assert_not_called()


class TestGenerateReflection:
    """Tests for the reflection generation pipeline."""

    @pytest.mark.unit
    @patch("memory_enhancement.hooks.session_end_memory.extract_session_facts")
    @patch("memory_enhancement.hooks.session_end_memory.apply_confidence_decay")
    @patch("memory_enhancement.hooks.session_end_memory.reinforce_memories")
    @patch("memory_enhancement.health.generate_health_report")
    def test_generates_reflection(
        self, mock_report, mock_reinforce, mock_decay, mock_facts, tmp_path: Path
    ):
        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()
        (memories_dir / "test.md").write_text("# Test (2026-01-01)\n\nContent\n")

        mock_reinforce.return_value = {"test": 0.85}
        mock_decay.return_value = []
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
        mock_reinforce.assert_called_once_with(memories_dir, tmp_path)
        mock_decay.assert_called_once_with(memories_dir, tmp_path)

    @pytest.mark.unit
    @patch("memory_enhancement.hooks.session_end_memory.extract_session_facts")
    @patch("memory_enhancement.hooks.session_end_memory.apply_confidence_decay")
    @patch("memory_enhancement.hooks.session_end_memory.reinforce_memories")
    @patch("memory_enhancement.health.generate_health_report")
    def test_empty_memories_returns_empty(
        self, mock_report, mock_reinforce, mock_decay, mock_facts, tmp_path: Path
    ):
        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()
        mock_reinforce.return_value = {}
        mock_decay.return_value = []
        mock_facts.return_value = []
        mock_report.return_value = MagicMock(total_memories=0)

        result = _generate_reflection(memories_dir, tmp_path)
        assert result == ""

    @pytest.mark.unit
    @patch("memory_enhancement.hooks.session_end_memory.extract_session_facts")
    @patch("memory_enhancement.hooks.session_end_memory.apply_confidence_decay")
    @patch("memory_enhancement.hooks.session_end_memory.reinforce_memories")
    @patch("memory_enhancement.health.generate_health_report")
    def test_decayed_memories_shown_in_reflection(
        self, mock_report, mock_reinforce, mock_decay, mock_facts, tmp_path: Path
    ):
        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()

        mock_reinforce.return_value = {"old1": 0.3, "old2": 0.2}
        mock_decay.return_value = ["old1", "old2"]
        mock_facts.return_value = []
        mock_report.return_value = MagicMock(
            total_memories=2,
            health_score=0.5,
            stale_memories=[],
            recommendations=[],
        )

        result = _generate_reflection(memories_dir, tmp_path)
        assert "Decayed: 2 exceed the age threshold" in result
