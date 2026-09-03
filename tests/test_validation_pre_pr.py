"""Core tests for scripts.validation.pre_pr orchestration."""

# taste-lint: ignore file-size, shared process fixtures and ordering assertions
# make splitting these orchestration tests into modules less clear to maintain.

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation.checks_tooling import validate_always_on_corpus_claims
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


def _sequence_with_passing_corpus_gates() -> tuple[Any, ...]:
    # pre_pr loads pre_pr_sequence as a flat module for direct script execution.
    # Read through the function so the patch targets that exact module identity.
    sequence = run_all_validations.__globals__["_SEQUENCE"]
    corpus_gates = {
        "Documented Interpreter Portability",
        "Duplicate Test Helper Detection",
        "Subprocess Encoding Convention",
        "Unreachable Code Detection",
        # Reads the real .git directory via `git rev-parse --git-path hooks`.
        # _healthy_git_run's rev-parse branch answers every rev-parse call with
        # "0" * 40 (a plausible commit SHA for HEAD-style queries), which this
        # gate's --git-path call turns into a nonsense path and then correctly
        # reports as unhealthy. The gate's own correctness against a real git
        # tree is covered by tests/validation/test_check_git_hook_health.py;
        # here it is real-git-state-dependent noise the same way the other
        # corpus gates are real-filesystem-dependent noise.
        "Git Hook Health (core.hooksPath)",
        # check_adr_links.py's validate_adr_links() calls `git ls-files -z
        # *.md` via git_ls_markdown(). _healthy_git_run's blanket
        # `else: stdout = ""` branch answers that call (it matches neither
        # "symbolic-ref" nor "rev-parse"), so git_ls_markdown() returns an
        # empty list under this mock regardless of the real repo's tracked
        # files. check_adr_links.py's round-9 fix (PR #5209) treats a
        # zero-file result as a wrong-but-valid repository root and fails
        # closed, which is correct against a real git invocation but is a
        # mock artifact here, not a real empty corpus: real-filesystem-
        # dependent noise the same way the other corpus gates above are.
        "ADR Link Resolution",
        # `check_index_line_endings.py` captures `git ls-files --eol -z` in
        # bytes, because a pathname is bytes and `errors="replace"` destroys
        # undecodable ones irreversibly (issue #5475). `_healthy_git_run`
        # answers every call with a `str` stdout, so the gate's `.decode` gets
        # an object that has no such method and the gate reports a mock
        # artifact rather than a line-ending verdict. The gate's own behavior
        # is covered across tests/validation/test_check_index_line_endings*.py,
        # whose roster lives in
        # tests/validation/index_line_endings_helpers.py rather than being
        # restated here, and the gate's registration is covered in
        # tests/validation/test_pre_pr_index_line_endings_wiring.py.
        "Index Line Endings",
    }
    return tuple(
        replace(gate, run=lambda _repo_root, _args: True)
        if gate.name in corpus_gates
        else gate
        for gate in sequence
    )


def _sequence_with_failing_python_syntax() -> tuple[Any, ...]:
    sequence = run_all_validations.__globals__["_SEQUENCE"]
    return tuple(
        replace(gate, run=lambda _repo_root, _args: False)
        if gate.name == "Python Syntax (compile gate)"
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
                return_value=(0, ".agents/sessions/2025-12-01-session-1.json\0", ""),
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
                return 0, ".agents/sessions/2025-12-01-session-1.json\0", ""
            if "rev-parse" in command:
                return 0, f"{head}\n", ""
            return 0, "", ""

        with patch(
            "checks_tooling._resolve_branch_base_ref",
            return_value="origin/main",
        ), patch(
            "checks_tooling.new_session_logs",
            return_value={".agents/sessions/2025-12-01-session-1.json"},
        ), patch("checks_tooling._run_subprocess", side_effect=fake_run):
            assert validate_session_end(tmp_path) is True

        assert seen[-1][-2:] == ["--validation-head", head]

    def test_existing_historical_log_is_validated_as_a_record(
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
        seen: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: Any) -> tuple[int, str, str]:
            seen.append(command)
            if "diff" in command:
                return 0, ".agents/sessions/2025-12-01-session-1.json\0", ""
            if "rev-parse" in command:
                return 0, f"{'c' * 40}\n", ""
            return 0, "", ""

        with patch(
            "checks_tooling._resolve_branch_base_ref",
            return_value="origin/main",
        ), patch(
            "checks_tooling.new_session_logs",
            return_value=set(),
        ), patch("checks_tooling._run_subprocess", side_effect=fake_run):
            assert validate_session_end(tmp_path) is True

        assert seen[-1][-1] == "--existing-log"
        assert "--validation-head" not in seen[-1]

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
                return 0, ".agents/sessions/2025-12-01-session-1.json\0", ""
            if "rev-parse" in command:
                return 1, "", "bad ref"
            return 1, "", "invalid validation head"

        with patch(
            "checks_tooling._resolve_branch_base_ref",
            return_value="origin/main",
        ), patch(
            "checks_tooling.new_session_logs",
            return_value={".agents/sessions/2025-12-01-session-1.json"},
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
        new_callable=_sequence_with_passing_corpus_gates,
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
        new_callable=_sequence_with_passing_corpus_gates,
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


class TestHookModeBanner:
    """The success banner must not claim PR-readiness when running as a hook job.

    Issue #4506: pre_pr.py runs in a parallel lefthook group alongside
    python-tests, ratchets, and other jobs. It only validates its own subset.
    Printing "Ready to create pull request!" is a false claim when sibling jobs
    may still be running or may have failed.

    SKIP_AUTOFIX=1 is the marker lefthook sets on the pre-pr-validation job
    (lefthook.yml lines 397-401). It is absent in direct interactive use.
    """

    @patch(
        "pre_pr_sequence._SEQUENCE",
        new_callable=_sequence_with_passing_corpus_gates,
    )
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_interactive_mode_prints_verification_guidance(
        self,
        mock_which: Any,
        mock_run: Any,
        _mock_sequence: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Direct invocation (no hook env) must print push-verification guidance."""
        mock_run.side_effect = _healthy_git_run
        mock_which.return_value = "/usr/bin/tool"

        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("SKIP_AUTOFIX", None)
            result = main(["--quick", "--skip-tests"])

        assert result == 0
        captured = capsys.readouterr()
        assert "Verify the push landed" in captured.out
        assert "same SHA" in captured.out
        assert "sibling hook jobs" not in captured.out

    @patch(
        "pre_pr_sequence._SEQUENCE",
        new_callable=_sequence_with_passing_corpus_gates,
    )
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_hook_mode_does_not_print_pr_ready_banner(
        self,
        mock_which: Any,
        mock_run: Any,
        _mock_sequence: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """SKIP_AUTOFIX=1 (hook mode) must suppress the PR-ready banner. Issue #4506."""
        mock_run.side_effect = _healthy_git_run
        mock_which.return_value = "/usr/bin/tool"

        with patch.dict("os.environ", {"SKIP_AUTOFIX": "1"}):
            result = main(["--quick", "--skip-tests"])

        assert result == 0
        captured = capsys.readouterr()
        assert "Verify the push landed" not in captured.out
        assert "sibling hook jobs" in captured.out

    @patch(
        "pre_pr_sequence._SEQUENCE",
        new_callable=_sequence_with_passing_corpus_gates,
    )
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_skip_autofix_zero_is_not_hook_mode(
        self,
        mock_which: Any,
        mock_run: Any,
        _mock_sequence: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """SKIP_AUTOFIX=0 is not hook mode; the verification guidance must still print."""
        mock_run.side_effect = _healthy_git_run
        mock_which.return_value = "/usr/bin/tool"

        with patch.dict("os.environ", {"SKIP_AUTOFIX": "0"}):
            result = main(["--quick", "--skip-tests"])

        assert result == 0
        captured = capsys.readouterr()
        assert "Verify the push landed" in captured.out

    @patch(
        "pre_pr_sequence._SEQUENCE",
        new_callable=_sequence_with_failing_python_syntax,
    )
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_hook_mode_failure_does_not_print_either_banner(
        self,
        mock_which: Any,
        mock_run: Any,
        _mock_sequence: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A failing run in hook mode must not print either banner."""
        mock_run.side_effect = _healthy_git_run
        mock_which.return_value = "/usr/bin/tool"

        with patch.dict("os.environ", {"SKIP_AUTOFIX": "1"}):
            result = main(["--quick", "--skip-tests"])

        assert result == 1
        captured = capsys.readouterr()
        assert "Verify the push landed" not in captured.out
        assert "sibling hook jobs" not in captured.out

    @patch(
        "pre_pr_sequence._SEQUENCE",
        new_callable=_sequence_with_passing_corpus_gates,
    )
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_success_output_requires_remote_sha_to_match_head(
        self,
        mock_which: Any,
        mock_run: Any,
        _mock_sequence: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Issue #4506: verification must reject an existing but stale remote ref."""
        mock_run.side_effect = _healthy_git_run
        mock_which.return_value = "/usr/bin/tool"

        result = main(["--quick", "--skip-tests"])
        assert result == 0
        out = capsys.readouterr().out
        assert "Verify the push landed" in out
        assert "git rev-parse HEAD" in out
        assert "git ls-remote origin <branch>" in out
        assert "same SHA" in out


def test_always_on_corpus_claims_skips_without_test_tree(tmp_path: Path) -> None:
    (tmp_path / ".github" / "instructions").mkdir(parents=True)
    missing_script_skip = validate_always_on_corpus_claims.__globals__["MissingScriptSkip"]

    with pytest.raises(missing_script_skip, match="no corpus claim test to run"):
        validate_always_on_corpus_claims(tmp_path)
