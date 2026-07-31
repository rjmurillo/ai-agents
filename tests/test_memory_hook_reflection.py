"""Tests for the session_end_memory hook (reflection)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from memory_enhancement.hooks.session_end_memory import (
    _find_repo_root,
    _format_reflection,
    _generate_reflection,
    main,
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


class TestCorpusIsNeverRewritten:
    """SessionEnd must leave .serena/memories byte-identical (issue #4011).

    The hook used to round-trip every memory through save_memory to persist a
    confidence score. Nothing reads a stored score (search recomputes it), and
    the round trip stripped every "## Links" block and stamped created_at with
    wall clock, so the first real session end left 879 tracked files dirty.
    """

    @staticmethod
    def _corpus(tmp_path: Path) -> Path:
        memories_dir = tmp_path / ".serena" / "memories"
        (memories_dir / "nested").mkdir(parents=True)
        (memories_dir / "plain.md").write_text(
            "# Plain (2026-01-01)\n\nBody text.\n\n"
            "## Links\n\n- [other](other.md): cross reference\n"
        )
        (memories_dir / "other.md").write_text("# Other (2026-01-01)\n\nBody.\n")
        (memories_dir / "nested" / "deep.md").write_text("# Deep (2026-01-01)\n\nBody.\n")
        return memories_dir

    @staticmethod
    def _snapshot(memories_dir: Path) -> dict[str, str]:
        return {
            str(path.relative_to(memories_dir)): path.read_text()
            for path in sorted(memories_dir.rglob("*.md"))
        }

    @pytest.mark.unit
    def test_generate_reflection_writes_nothing(self, tmp_path: Path):
        memories_dir = self._corpus(tmp_path)
        before = self._snapshot(memories_dir)

        summary = _generate_reflection(memories_dir, tmp_path)

        assert "<session-reflection>" in summary
        assert self._snapshot(memories_dir) == before

    @pytest.mark.unit
    def test_link_block_survives_a_second_run(self, tmp_path: Path):
        memories_dir = self._corpus(tmp_path)

        _generate_reflection(memories_dir, tmp_path)
        _generate_reflection(memories_dir, tmp_path)

        assert "## Links" in (memories_dir / "plain.md").read_text()
        assert "created_at" not in (memories_dir / "other.md").read_text()

    @pytest.mark.unit
    def test_main_writes_nothing_end_to_end(self, tmp_path: Path, monkeypatch):
        memories_dir = self._corpus(tmp_path)
        before = self._snapshot(memories_dir)
        monkeypatch.setattr(
            "memory_enhancement.hooks.session_end_memory._find_repo_root",
            lambda start=None: tmp_path,
        )

        exit_code = main()

        assert exit_code == 0
        assert self._snapshot(memories_dir) == before

    @pytest.mark.unit
    def test_reflection_module_has_no_writer(self):
        import memory_enhancement.reflection as reflection

        assert not hasattr(reflection, "save_memory")
        assert not hasattr(reflection, "reinforce_memories")


class TestGenerateReflection:
    """Tests for the reflection generation pipeline."""

    @pytest.mark.unit
    @patch("memory_enhancement.hooks.session_end_memory.extract_session_facts")
    @patch("memory_enhancement.hooks.session_end_memory.apply_confidence_decay")
    @patch("memory_enhancement.hooks.session_end_memory.update_confidence_scores_with_memories")
    @patch("memory_enhancement.health.generate_health_report")
    def test_generates_reflection(
        self, mock_report, mock_scores, mock_decay, mock_facts, tmp_path: Path
    ):
        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()
        (memories_dir / "test.md").write_text("# Test (2026-01-01)\n\nContent\n")

        mock_scores.return_value = ({"test": 0.85}, [])
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
        mock_scores.assert_called_once_with(memories_dir, tmp_path)
        mock_decay.assert_called_once_with(memories_dir, tmp_path)

    @pytest.mark.unit
    @patch("memory_enhancement.hooks.session_end_memory.extract_session_facts")
    @patch("memory_enhancement.hooks.session_end_memory.apply_confidence_decay")
    @patch("memory_enhancement.hooks.session_end_memory.update_confidence_scores_with_memories")
    @patch("memory_enhancement.health.generate_health_report")
    def test_empty_memories_returns_empty(
        self, mock_report, mock_scores, mock_decay, mock_facts, tmp_path: Path
    ):
        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()
        mock_scores.return_value = ({}, [])
        mock_decay.return_value = []
        mock_facts.return_value = []
        mock_report.return_value = MagicMock(total_memories=0)

        result = _generate_reflection(memories_dir, tmp_path)
        assert result == ""

    @pytest.mark.unit
    @patch("memory_enhancement.hooks.session_end_memory.extract_session_facts")
    @patch("memory_enhancement.hooks.session_end_memory.apply_confidence_decay")
    @patch("memory_enhancement.hooks.session_end_memory.update_confidence_scores_with_memories")
    @patch("memory_enhancement.health.generate_health_report")
    def test_decayed_memories_shown_in_reflection(
        self, mock_report, mock_scores, mock_decay, mock_facts, tmp_path: Path
    ):
        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()

        mock_scores.return_value = ({"old1": 0.3, "old2": 0.2}, [])
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


class TestExitContract:
    """SessionEnd cannot inject context, so exit 2 buys nothing (issue #4011).

    The summary is the whole output, and it must reach stderr on the path that
    returns 0.
    """

    @staticmethod
    def _repo(tmp_path: Path):
        (tmp_path / ".serena" / "memories").mkdir(parents=True)
        return tmp_path

    @pytest.mark.unit
    def test_summary_goes_to_stderr_and_returns_zero(self, tmp_path, monkeypatch, capsys):
        repo = self._repo(tmp_path)
        monkeypatch.setattr(
            "memory_enhancement.hooks.session_end_memory._find_repo_root",
            lambda start=None: repo,
        )
        monkeypatch.setattr(
            "memory_enhancement.hooks.session_end_memory._generate_reflection",
            lambda *_args: "<session-reflection>ok</session-reflection>",
        )

        exit_code = main()

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "<session-reflection>" in captured.err
        assert captured.out == ""

    @pytest.mark.unit
    def test_scoring_runs_on_the_zero_exit_path(self, tmp_path, monkeypatch):
        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()
        calls: list[Path] = []

        def fake_scores(mem_dir, _repo_root):
            calls.append(mem_dir)
            return {}, []

        monkeypatch.setattr(
            "memory_enhancement.hooks.session_end_memory."
            "update_confidence_scores_with_memories",
            fake_scores,
        )
        monkeypatch.setattr(
            "memory_enhancement.hooks.session_end_memory.extract_session_facts",
            lambda _mem_dir: [],
        )
        monkeypatch.setattr(
            "memory_enhancement.hooks.session_end_memory.apply_confidence_decay",
            lambda _mem_dir, _repo_root: [],
        )
        monkeypatch.setattr(
            "memory_enhancement.health.generate_health_report",
            lambda *_args, **_kwargs: MagicMock(
                total_memories=1, health_score=1.0, stale_memories=[], recommendations=[]
            ),
        )

        _generate_reflection(memories_dir, tmp_path)

        assert calls == [memories_dir]

    @pytest.mark.unit
    def test_missing_memories_dir_returns_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "memory_enhancement.hooks.session_end_memory._find_repo_root",
            lambda start=None: tmp_path,
        )

        assert main() == 0

    @pytest.mark.unit
    def test_no_repo_root_returns_zero(self, monkeypatch):
        monkeypatch.setattr(
            "memory_enhancement.hooks.session_end_memory._find_repo_root",
            lambda start=None: None,
        )

        assert main() == 0
