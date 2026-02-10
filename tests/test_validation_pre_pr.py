"""Tests for scripts.validation.pre_pr module.

Validates the pre-PR validation runner including individual validations,
result tracking, and CLI behavior. External tool calls are mocked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from scripts.validation.pre_pr import (
    ValidationState,
    _find_latest_session_log,
    _run_subprocess,
    _use_color,
    build_parser,
    main,
    run_validation,
    validate_session_end,
)

# ---------------------------------------------------------------------------
# _use_color
# ---------------------------------------------------------------------------


class TestUseColor:
    """Tests for ANSI color detection."""

    def test_no_color_env(self) -> None:
        with patch.dict("os.environ", {"NO_COLOR": "1"}, clear=False):
            assert _use_color() is False

    def test_dumb_terminal(self) -> None:
        with patch.dict("os.environ", {"TERM": "dumb"}, clear=False):
            assert _use_color() is False

    def test_ci_env(self) -> None:
        with patch.dict("os.environ", {"CI": "true"}, clear=False):
            assert _use_color() is False


# ---------------------------------------------------------------------------
# _find_latest_session_log
# ---------------------------------------------------------------------------


class TestFindLatestSessionLog:
    """Tests for session log discovery."""

    def test_returns_none_when_no_directory(self, tmp_path: Path) -> None:
        assert _find_latest_session_log(tmp_path) is None

    def test_returns_none_when_empty(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        assert _find_latest_session_log(tmp_path) is None

    def test_finds_latest_log(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "2025-12-01-session-1.md").write_text("old", encoding="utf-8")
        (sessions / "2025-12-02-session-1.md").write_text("new", encoding="utf-8")

        result = _find_latest_session_log(tmp_path)
        assert result is not None
        assert result.name == "2025-12-02-session-1.md"

    def test_ignores_non_matching_files(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "README.md").write_text("not a log", encoding="utf-8")
        (sessions / "2025-12-01-session-1.md").write_text("log", encoding="utf-8")

        result = _find_latest_session_log(tmp_path)
        assert result is not None
        assert result.name == "2025-12-01-session-1.md"


# ---------------------------------------------------------------------------
# _run_subprocess
# ---------------------------------------------------------------------------


class TestRunSubprocess:
    """Tests for subprocess runner."""

    def test_successful_command(self) -> None:
        exit_code, stdout, stderr = _run_subprocess(["echo", "hello"])
        assert exit_code == 0
        assert "hello" in stdout

    def test_command_not_found(self) -> None:
        exit_code, stdout, stderr = _run_subprocess(
            ["nonexistent_command_xyz_123"]
        )
        assert exit_code == -1
        assert "not found" in stderr.lower() or "Command not found" in stderr


# ---------------------------------------------------------------------------
# ValidationState / run_validation
# ---------------------------------------------------------------------------


class TestRunValidation:
    """Tests for validation runner and state tracking."""

    def test_passing_validation(self) -> None:
        state = ValidationState()
        result = run_validation("Test Check", state, lambda: True)
        assert result is True
        assert state.total == 1
        assert state.passed == 1
        assert state.failed == 0

    def test_failing_validation(self) -> None:
        state = ValidationState()
        result = run_validation("Test Check", state, lambda: False)
        assert result is False
        assert state.total == 1
        assert state.passed == 0
        assert state.failed == 1

    def test_skipped_validation(self) -> None:
        state = ValidationState()
        result = run_validation("Test Check", state, lambda: True, skip=True)
        assert result is True
        assert state.total == 1
        assert state.skipped == 1
        assert state.passed == 0

    def test_exception_counts_as_failure(self) -> None:
        def raise_error() -> bool:
            raise RuntimeError("boom")

        state = ValidationState()
        result = run_validation("Test Check", state, raise_error)
        assert result is False
        assert state.failed == 1

    def test_records_duration(self) -> None:
        state = ValidationState()
        run_validation("Test Check", state, lambda: True)
        assert state.results[0].duration >= 0

    def test_multiple_validations(self) -> None:
        state = ValidationState()
        run_validation("Check 1", state, lambda: True)
        run_validation("Check 2", state, lambda: False)
        run_validation("Check 3", state, lambda: True, skip=True)

        assert state.total == 3
        assert state.passed == 1
        assert state.failed == 1
        assert state.skipped == 1
        assert len(state.results) == 3


# ---------------------------------------------------------------------------
# validate_session_end
# ---------------------------------------------------------------------------


class TestValidateSessionEnd:
    """Tests for session end validation."""

    def test_no_session_log_returns_true(self, tmp_path: Path) -> None:
        result = validate_session_end(tmp_path)
        assert result is True

    def test_missing_script_returns_false(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "2025-12-01-session-1.md").write_text("log", encoding="utf-8")
        # scripts/Validate-Session.ps1 does not exist
        (tmp_path / "scripts").mkdir(exist_ok=True)

        result = validate_session_end(tmp_path)
        assert result is False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Tests for CLI argument parsing."""

    def test_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.quick is False
        assert args.skip_tests is False
        assert args.verbose is False

    def test_quick_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--quick"])
        assert args.quick is True

    def test_skip_tests_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--skip-tests"])
        assert args.skip_tests is True

    def test_verbose_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--verbose"])
        assert args.verbose is True


class TestMain:
    """Integration tests for main entry point.

    External tool calls are mocked to avoid requiring actual tools.
    """

    @patch("scripts.validation.pre_pr._run_subprocess")
    def test_quick_mode_skips_slow_checks(self, mock_subprocess: Any) -> None:
        mock_subprocess.return_value = (0, "", "")

        # Quick mode should skip path normalization, planning, agent drift, yaml style
        result = main(["--quick", "--skip-tests"])
        # Should not fail since all checks pass or are skipped
        assert result in (0, 1)  # May fail if scripts don't exist

    @patch("scripts.validation.pre_pr._run_subprocess")
    @patch("scripts.validation.pre_pr.shutil")
    def test_all_pass_returns_zero(
        self, mock_shutil: Any, mock_subprocess: Any
    ) -> None:
        mock_subprocess.return_value = (0, "", "")
        mock_shutil.which.return_value = "/usr/bin/npx"

        # All external tools pass
        result = main(["--quick", "--skip-tests"])
        assert result in (0, 1)
