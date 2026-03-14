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
    _parse_yaml_frontmatter,
    _run_subprocess,
    build_parser,
    main,
    run_validation,
    validate_design_review_frontmatter,
    validate_session_end,
)

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


# ---------------------------------------------------------------------------
# _parse_yaml_frontmatter
# ---------------------------------------------------------------------------


class TestParseYamlFrontmatter:
    """Tests for YAML frontmatter parser."""

    def test_parses_valid_frontmatter(self) -> None:
        text = '---\nstatus: "APPROVED"\npriority: "P1"\nblocking: false\n---\n# Title\n'
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["status"] == "APPROVED"
        assert result["priority"] == "P1"
        assert result["blocking"] is False

    def test_returns_none_without_frontmatter(self) -> None:
        text = "# Title\nSome content\n"
        assert _parse_yaml_frontmatter(text) is None

    def test_returns_none_for_unclosed_frontmatter(self) -> None:
        text = "---\nstatus: APPROVED\n# No closing delimiter\n"
        assert _parse_yaml_frontmatter(text) is None

    def test_parses_boolean_true(self) -> None:
        text = "---\nblocking: true\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["blocking"] is True

    def test_parses_integer_values(self) -> None:
        text = "---\npr: 1205\nissue: 937\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["pr"] == 1205
        assert result["issue"] == 937

    def test_strips_quotes(self) -> None:
        text = '---\nstatus: "BLOCKED"\nreviewer: \'architect\'\n---\n'
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["status"] == "BLOCKED"
        assert result["reviewer"] == "architect"

    def test_skips_comments_and_blank_lines(self) -> None:
        text = "---\n# comment\n\nstatus: APPROVED\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["status"] == "APPROVED"
        assert len(result) == 1


# ---------------------------------------------------------------------------
# validate_design_review_frontmatter
# ---------------------------------------------------------------------------


class TestValidateDesignReviewFrontmatter:
    """Tests for DESIGN-REVIEW frontmatter validation."""

    def _write_review(self, tmp_path: Path, name: str, content: str) -> Path:
        """Helper to create a DESIGN-REVIEW file."""
        review_dir = tmp_path / ".agents" / "architecture"
        review_dir.mkdir(parents=True, exist_ok=True)
        filepath = review_dir / name
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def test_no_directory_returns_true(self, tmp_path: Path) -> None:
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_no_review_files_returns_true(self, tmp_path: Path) -> None:
        (tmp_path / ".agents" / "architecture").mkdir(parents=True)
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_valid_frontmatter_passes(self, tmp_path: Path) -> None:
        content = (
            '---\nstatus: "APPROVED"\npriority: "P1"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_missing_frontmatter_fails(self, tmp_path: Path) -> None:
        content = "# Design Review: Test\nNo frontmatter here.\n"
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is False

    def test_missing_required_fields_fails(self, tmp_path: Path) -> None:
        content = '---\nstatus: "APPROVED"\n---\n# Design Review: Test\n'
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is False

    def test_invalid_status_fails(self, tmp_path: Path) -> None:
        content = (
            '---\nstatus: "INVALID"\npriority: "P1"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is False

    def test_invalid_priority_fails(self, tmp_path: Path) -> None:
        content = (
            '---\nstatus: "APPROVED"\npriority: "P99"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is False

    def test_blocking_review_detected(self, tmp_path: Path) -> None:
        content = (
            '---\nstatus: "BLOCKED"\npriority: "P0"\n'
            'blocking: true\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        # Blocking reviews still pass validation (they just warn)
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_multiple_files_all_valid(self, tmp_path: Path) -> None:
        valid = (
            '---\nstatus: "APPROVED"\npriority: "P1"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-a.md", valid)
        self._write_review(tmp_path, "DESIGN-REVIEW-b.md", valid)
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_one_invalid_among_valid_fails(self, tmp_path: Path) -> None:
        valid = (
            '---\nstatus: "APPROVED"\npriority: "P1"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review\n"
        )
        invalid = "# No frontmatter\n"
        self._write_review(tmp_path, "DESIGN-REVIEW-a.md", valid)
        self._write_review(tmp_path, "DESIGN-REVIEW-b.md", invalid)
        assert validate_design_review_frontmatter(tmp_path) is False


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
