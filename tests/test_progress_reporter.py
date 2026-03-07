"""Tests for progress reporting module.

Tests the session and skill-level progress indicators per Issue #670.
"""

from __future__ import annotations

import pytest

from scripts.progress import ProgressReporter, emit_checkpoint, is_quiet_mode


class TestIsQuietMode:
    """Tests for quiet mode detection."""

    def test_returns_false_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Quiet mode is disabled when env var is not set."""
        monkeypatch.delenv("CLAUDE_PROGRESS_QUIET", raising=False)
        assert is_quiet_mode() is False

    def test_returns_true_when_set_to_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Quiet mode enabled with value '1'."""
        monkeypatch.setenv("CLAUDE_PROGRESS_QUIET", "1")
        assert is_quiet_mode() is True

    def test_returns_true_when_set_to_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Quiet mode enabled with value 'true'."""
        monkeypatch.setenv("CLAUDE_PROGRESS_QUIET", "true")
        assert is_quiet_mode() is True

    def test_returns_true_when_set_to_yes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Quiet mode enabled with value 'yes'."""
        monkeypatch.setenv("CLAUDE_PROGRESS_QUIET", "yes")
        assert is_quiet_mode() is True

    def test_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Quiet mode detection is case-insensitive."""
        monkeypatch.setenv("CLAUDE_PROGRESS_QUIET", "TRUE")
        assert is_quiet_mode() is True

    def test_returns_false_for_other_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Other values do not enable quiet mode."""
        monkeypatch.setenv("CLAUDE_PROGRESS_QUIET", "0")
        assert is_quiet_mode() is False


class TestEmitCheckpoint:
    """Tests for checkpoint emission."""

    def test_emits_basic_checkpoint(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Basic checkpoint with step name only."""
        monkeypatch.delenv("CLAUDE_PROGRESS_QUIET", raising=False)
        emit_checkpoint("Processing files")
        captured = capsys.readouterr()
        assert "[CHECKPOINT] Processing files" in captured.err

    def test_emits_checkpoint_with_progress(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Checkpoint with current/total progress numbers."""
        monkeypatch.delenv("CLAUDE_PROGRESS_QUIET", raising=False)
        emit_checkpoint("Scanning", current=5, total=20)
        captured = capsys.readouterr()
        assert "[CHECKPOINT] Scanning (5/20)" in captured.err

    def test_emits_checkpoint_with_current_only(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Checkpoint with current count only (no total)."""
        monkeypatch.delenv("CLAUDE_PROGRESS_QUIET", raising=False)
        emit_checkpoint("Processing", current=10)
        captured = capsys.readouterr()
        assert "[CHECKPOINT] Processing (10)" in captured.err

    def test_emits_checkpoint_with_details(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Checkpoint with additional details."""
        monkeypatch.delenv("CLAUDE_PROGRESS_QUIET", raising=False)
        emit_checkpoint("Validating", details="config.yaml")
        captured = capsys.readouterr()
        assert "[CHECKPOINT] Validating : config.yaml" in captured.err

    def test_emits_full_checkpoint(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Checkpoint with all fields."""
        monkeypatch.delenv("CLAUDE_PROGRESS_QUIET", raising=False)
        emit_checkpoint("Processing", current=5, total=20, details="src/main.py")
        captured = capsys.readouterr()
        assert "[CHECKPOINT] Processing (5/20) : src/main.py" in captured.err

    def test_suppressed_in_quiet_mode(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Checkpoint output suppressed when quiet mode enabled."""
        monkeypatch.setenv("CLAUDE_PROGRESS_QUIET", "1")
        emit_checkpoint("Processing files")
        captured = capsys.readouterr()
        assert captured.err == ""


class TestProgressReporter:
    """Tests for session-level progress reporter."""

    def test_start_phase_emits_progress(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Starting a phase emits progress message."""
        monkeypatch.delenv("CLAUDE_PROGRESS_QUIET", raising=False)
        reporter = ProgressReporter(total_steps=3)
        reporter.start_phase("Initialization")
        captured = capsys.readouterr()
        assert "[PROGRESS]" in captured.err
        assert "Starting: Initialization" in captured.err
        assert "[0/3]" in captured.err
        assert "(0%)" in captured.err

    def test_complete_step_increments_counter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Completing a step increments the completed counter."""
        monkeypatch.setenv("CLAUDE_PROGRESS_QUIET", "1")  # Suppress output
        reporter = ProgressReporter(total_steps=3)
        assert reporter.completed_steps == 0
        reporter.start_phase("Test")
        reporter.complete_step()
        assert reporter.completed_steps == 1

    def test_complete_step_emits_progress(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Completing a step emits progress message."""
        monkeypatch.delenv("CLAUDE_PROGRESS_QUIET", raising=False)
        reporter = ProgressReporter(total_steps=3)
        reporter.start_phase("Processing")
        capsys.readouterr()  # Clear start message
        reporter.complete_step()
        captured = capsys.readouterr()
        assert "[PROGRESS]" in captured.err
        assert "Completed: Processing" in captured.err
        assert "[1/3]" in captured.err
        assert "(33%)" in captured.err

    def test_complete_step_with_result(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Completing a step with result includes result in output."""
        monkeypatch.delenv("CLAUDE_PROGRESS_QUIET", raising=False)
        reporter = ProgressReporter(total_steps=2)
        reporter.start_phase("Analysis")
        capsys.readouterr()  # Clear start message
        reporter.complete_step(result="5 issues found")
        captured = capsys.readouterr()
        assert "5 issues found" in captured.err

    def test_invoke_skill_records_and_emits(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Invoking a skill records it and emits message."""
        monkeypatch.delenv("CLAUDE_PROGRESS_QUIET", raising=False)
        reporter = ProgressReporter()
        reporter.invoke_skill("pr-review")
        captured = capsys.readouterr()
        assert "[SKILL] Invoking: pr-review" in captured.err
        assert reporter.skills_invoked == ["pr-review"]

    def test_report_summary_shows_stats(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Summary shows completed steps and skills."""
        monkeypatch.delenv("CLAUDE_PROGRESS_QUIET", raising=False)
        reporter = ProgressReporter(total_steps=2)
        reporter.start_phase("Step1")
        reporter.complete_step()
        reporter.invoke_skill("test-skill")
        capsys.readouterr()  # Clear intermediate output
        reporter.report_summary()
        captured = capsys.readouterr()
        assert "[SUMMARY]" in captured.err
        assert "Steps: 1/2" in captured.err
        assert "Skills: test-skill" in captured.err

    def test_suppressed_in_quiet_mode(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """All output suppressed in quiet mode."""
        monkeypatch.setenv("CLAUDE_PROGRESS_QUIET", "1")
        reporter = ProgressReporter(total_steps=2)
        reporter.start_phase("Test")
        reporter.invoke_skill("skill")
        reporter.complete_step()
        reporter.report_summary()
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_progress_without_total_steps(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Progress works without knowing total steps."""
        monkeypatch.delenv("CLAUDE_PROGRESS_QUIET", raising=False)
        reporter = ProgressReporter()  # No total_steps
        reporter.start_phase("Dynamic")
        captured = capsys.readouterr()
        assert "[0]" in captured.err  # Shows count without percentage


class TestProgressReporterIntegration:
    """Integration tests for complete workflows."""

    def test_full_workflow(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test a complete session workflow."""
        monkeypatch.delenv("CLAUDE_PROGRESS_QUIET", raising=False)

        reporter = ProgressReporter(total_steps=3)

        reporter.start_phase("Initialization")
        reporter.complete_step()

        reporter.start_phase("Processing")
        reporter.invoke_skill("pr-review")
        reporter.complete_step(result="5 files processed")

        reporter.start_phase("Cleanup")
        reporter.complete_step()

        reporter.report_summary()

        captured = capsys.readouterr()
        output = captured.err

        # Verify key milestones in order
        assert "Starting: Initialization" in output
        assert "Completed: Initialization" in output
        assert "Starting: Processing" in output
        assert "Invoking: pr-review" in output
        assert "5 files processed" in output
        assert "Starting: Cleanup" in output
        assert "[SUMMARY]" in output
        assert "Steps: 3/3" in output
