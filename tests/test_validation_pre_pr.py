"""Core tests for scripts.validation.pre_pr orchestration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation.pre_pr import (
    ValidationState,
    _find_latest_session_log,
    _run_subprocess,
    build_parser,
    main,
    run_all_validations,
    run_validation,
    validate_session_end,
)


def _sequence_with_passing_doc_interpreter() -> tuple[Any, ...]:
    # pre_pr loads pre_pr_sequence as a flat module for direct script execution.
    # Read through the function so the patch targets that exact module identity.
    sequence = run_all_validations.__globals__["_SEQUENCE"]
    return tuple(
        replace(gate, run=lambda _repo_root, _args: True)
        if gate.name == "Documented Interpreter Portability"
        else gate
        for gate in sequence
    )


def _healthy_git_run(*args: Any, **_kwargs: Any) -> Any:
    """Model a working toolchain: every tool exits 0, git answers plausibly.

    A blanket ``stdout = ""`` makes ``git symbolic-ref --short
    refs/remotes/origin/HEAD`` look like a repository with no remote HEAD, and
    the count-ratchet gate fails closed on exactly that. Answering per command
    keeps these tests on the all-pass path without feeding a branch name to
    every other gate that reads stdout.
    """
    argv = args[0] if args else []
    if "symbolic-ref" in argv:
        stdout = "origin/main"
    elif "rev-parse" in argv:
        stdout = "0" * 40
    else:
        stdout = ""
    return SimpleNamespace(returncode=0, stdout=stdout, stderr="")


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

    def test_missing_script_skip_does_not_fail(self) -> None:
        """MissingScriptSkip should be reported as SKIP, not FAIL.

        Regression guard for issue #1850: pre_pr.py must not produce FAIL
        lines for PowerShell scripts expunged per ADR-042.
        """
        from scripts.validation.pre_pr import MissingScriptSkip

        def raise_skip() -> bool:
            raise MissingScriptSkip("Some-Validator.ps1 not present")

        state = ValidationState()
        result = run_validation("Test Check", state, raise_skip)
        assert result is True  # SKIP must not block the gate
        assert state.skipped == 1
        assert state.failed == 0
        assert state.passed == 0
        assert state.results[0].status == "SKIP"

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


class TestValidateSessionEnd:
    """Tests for session end validation."""

    def test_no_session_log_returns_true(self, tmp_path: Path) -> None:
        result = validate_session_end(tmp_path)
        assert result is True

    def test_missing_script_raises_skip(self, tmp_path: Path) -> None:
        """When validate_session_json.py is absent and there ARE changed logs,
        the gate raises MissingScriptSkip (downstream install scenario)."""
        from unittest.mock import patch

        from scripts.validation.pre_pr import MissingScriptSkip

        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "2025-12-01-session-1.json").write_text("{}", encoding="utf-8")
        # No scripts/validate_session_json.py at tmp_path.
        (tmp_path / "scripts").mkdir(exist_ok=True)

        # Patch _resolve_branch_base_ref to return a ref (so the gate tries to
        # run rather than skipping on "no base ref"), and _run_subprocess to
        # return the session log in the diff.
        with patch(
            "checks_tooling._resolve_branch_base_ref", return_value="main"
        ):
            with patch(
                "checks_tooling._run_subprocess",
                return_value=(0, ".agents/sessions/2025-12-01-session-1.json\n", ""),
            ):
                with pytest.raises(MissingScriptSkip):
                    validate_session_end(tmp_path)

    def test_changed_log_is_validated_through_current_head(
        self, tmp_path: Path
    ) -> None:
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        log = sessions / "2025-12-01-session-1.json"
        log.write_text("{}", encoding="utf-8")
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        validator = scripts / "validate_session_json.py"
        validator.write_text("", encoding="utf-8")
        head = "c" * 40
        seen: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: Any) -> tuple[int, str, str]:
            seen.append(command)
            if "diff" in command:
                return 0, ".agents/sessions/2025-12-01-session-1.json\n", ""
            if "rev-parse" in command:
                return 0, f"{head}\n", ""
            return 0, "", ""

        with patch(
            "checks_tooling._resolve_branch_base_ref",
            return_value="origin/main",
        ), patch("checks_tooling._run_subprocess", side_effect=fake_run):
            assert validate_session_end(tmp_path) is True

        assert seen[-1][-2:] == ["--validation-head", head]

    def test_unresolvable_head_fails_closed(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        log = sessions / "2025-12-01-session-1.json"
        log.write_text("{}", encoding="utf-8")
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "validate_session_json.py").write_text("", encoding="utf-8")
        seen: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: Any) -> tuple[int, str, str]:
            seen.append(command)
            if "diff" in command:
                return 0, ".agents/sessions/2025-12-01-session-1.json\n", ""
            if "rev-parse" in command:
                return 1, "", "bad ref"
            return 1, "", "invalid validation head"

        with patch(
            "checks_tooling._resolve_branch_base_ref",
            return_value="origin/main",
        ), patch("checks_tooling._run_subprocess", side_effect=fake_run):
            assert validate_session_end(tmp_path) is False

        assert seen[-1][-2:] == ["--validation-head", "INVALID_HEAD"]


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

    @patch(
        "pre_pr_sequence._SEQUENCE",
        new_callable=_sequence_with_passing_doc_interpreter,
    )
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_quick_mode_skips_slow_checks(
        self,
        mock_which: Any,
        mock_run: Any,
        _mock_sequence: Any,
    ) -> None:
        mock_run.side_effect = _healthy_git_run
        mock_which.return_value = "/usr/bin/tool"

        # Quick mode should skip path normalization, planning, agent drift, yaml style
        result = main(["--quick", "--skip-tests"])
        assert result == 0

    @patch(
        "pre_pr_sequence._SEQUENCE",
        new_callable=_sequence_with_passing_doc_interpreter,
    )
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_all_pass_returns_zero(
        self,
        mock_which: Any,
        mock_run: Any,
        _mock_sequence: Any,
    ) -> None:
        mock_run.side_effect = _healthy_git_run
        mock_which.return_value = "/usr/bin/tool"

        # All external tools pass
        result = main(["--quick", "--skip-tests"])
        assert result == 0
