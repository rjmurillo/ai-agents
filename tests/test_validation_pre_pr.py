"""Core tests for scripts.validation.pre_pr orchestration."""

# taste-lint: ignore file-size, shared process fixtures and ordering assertions
# make splitting these orchestration tests into modules less clear to maintain.

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation.checks_tooling import validate_always_on_corpus_claims
from scripts.validation.evidence import (
    REASON_BASE_REF_UNRESOLVED,
    REASON_INCOMPLETE_EVIDENCE,
    EvidenceState,
)
from scripts.validation.pre_pr import (
    ValidationState,
    _find_latest_session_log,
    _run_subprocess,
    build_parser,
    main,
    run_validation,
    validate_session_end,
)


class TestFindLatestSessionLog:
    """Tests for session log discovery."""

    def test_returns_none_when_no_directory(self, tmp_path: Path) -> None:
        assert _find_latest_session_log(tmp_path) is None

    def test_returns_none_when_empty(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".project-toolkit" / "sessions"
        sessions.mkdir(parents=True)
        assert _find_latest_session_log(tmp_path) is None

    def test_finds_latest_log(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".project-toolkit" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "2025-12-01-session-1.md").write_text("old", encoding="utf-8")
        (sessions / "2025-12-02-session-1.md").write_text("new", encoding="utf-8")

        result = _find_latest_session_log(tmp_path)
        assert result is not None
        assert result.name == "2025-12-02-session-1.md"

    def test_ignores_non_matching_files(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".project-toolkit" / "sessions"
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

    def test_unresolvable_base_ref_reports_blocked(self, tmp_path: Path) -> None:
        """tmp_path is not a git checkout, so no base ref resolves.

        This test used to assert ``is True`` and was named
        ``test_no_session_log_returns_true``. It pinned the defect issue #5635
        exists to remove: a gate that could not compute its changed-file set
        reported the same value as a gate that computed an empty one. The name
        was wrong too, since no session log was ever examined.
        """
        result = validate_session_end(tmp_path)

        assert result.state is EvidenceState.BLOCKED
        assert result.reason == REASON_BASE_REF_UNRESOLVED
        assert result.examined is None

    def test_missing_script_raises_skip(self, tmp_path: Path) -> None:
        """When validate_session_json.py is absent and there ARE changed logs,
        the gate raises MissingScriptSkip (downstream install scenario)."""
        from unittest.mock import patch

        from scripts.validation.pre_pr import MissingScriptSkip

        sessions = tmp_path / ".project-toolkit" / "sessions"
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
                return_value=(0, ".project-toolkit/sessions/2025-12-01-session-1.json\0", ""),
            ):
                with pytest.raises(MissingScriptSkip):
                    validate_session_end(tmp_path)

    def test_changed_log_is_validated_through_current_head(
        self, tmp_path: Path
    ) -> None:
        sessions = tmp_path / ".project-toolkit" / "sessions"
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
                return 0, ".project-toolkit/sessions/2025-12-01-session-1.json\0", ""
            if "rev-parse" in command:
                return 0, f"{head}\n", ""
            return 0, "", ""

        with patch(
            "checks_tooling._resolve_branch_base_ref",
            return_value="origin/main",
        ), patch(
            "checks_tooling.new_session_logs",
            return_value={".project-toolkit/sessions/2025-12-01-session-1.json"},
        ), patch("checks_tooling._run_subprocess", side_effect=fake_run):
            assert validate_session_end(tmp_path).state is EvidenceState.PASS

        assert seen[-1][-2:] == ["--validation-head", head]

    def test_existing_historical_log_is_validated_as_a_record(
        self, tmp_path: Path
    ) -> None:
        sessions = tmp_path / ".project-toolkit" / "sessions"
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
                return 0, ".project-toolkit/sessions/2025-12-01-session-1.json\0", ""
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
            assert validate_session_end(tmp_path).state is EvidenceState.PASS

        assert seen[-1][-1] == "--existing-log"
        assert "--validation-head" not in seen[-1]

    def test_unresolvable_head_reports_unknown(self, tmp_path: Path) -> None:
        """Was test_unresolvable_head_fails_closed (issue #5646 item 2).

        The old contract let ``git rev-parse HEAD`` fail, substituted the
        literal ``INVALID_HEAD``, passed that to the child validator as
        ``--validation-head``, and reported the child's non-zero exit as FAIL.
        FAIL was the wrong finding: nothing about the session logs was proven,
        and a reader sent to fix a session log would find nothing wrong with it.
        The run now stops at the unreadable revision and says so.
        """
        sessions = tmp_path / ".project-toolkit" / "sessions"
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
                return 0, ".project-toolkit/sessions/2025-12-01-session-1.json\0", ""
            if "rev-parse" in command:
                return 1, "", "bad ref"
            return 1, "", "invalid validation head"

        with patch(
            "checks_tooling._resolve_branch_base_ref",
            return_value="origin/main",
        ), patch(
            "checks_tooling.new_session_logs",
            return_value={".project-toolkit/sessions/2025-12-01-session-1.json"},
        ), patch("checks_tooling._run_subprocess", side_effect=fake_run):
            outcome = validate_session_end(tmp_path)

        assert outcome.state is EvidenceState.UNKNOWN
        assert outcome.reason == REASON_INCOMPLETE_EVIDENCE
        # The child validator is never reached, so the placeholder that used to
        # travel to it as ``--validation-head`` cannot exist to be passed.
        assert all("--validation-head" not in command for command in seen)
        assert all("INVALID_HEAD" not in command for command in seen)


class TestBuildParser:
    """Tests for CLI argument parsing."""

    def test_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.quick is False

    def test_quick_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--quick"])
        assert args.quick is True

    def test_markdown_lint_only_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--markdown-lint-only", "README.md"])
        assert (args.markdown_lint_only, args.markdown_files) == (True, ["README.md"])

    def test_parser_declares_no_argument_the_runner_ignores(self) -> None:
        """Every declared destination must be read by pre_pr or the sequence.

        The defect this pins: --skip-tests and --verbose were declared, parsed,
        and never read by any consumer, so the parser advertised behavior the
        runner did not have. Asserting the destination set (rather than the
        absence of two names) also fails when a future flag is added without a
        consumer.

        ``summary_json`` joined the set with issue #5635; ``main`` reads it in
        ``_write_summary_json``.
        """
        dests = {
            action.dest
            for action in build_parser()._actions
            if action.dest != "help"
        }
        assert dests == {"quick", "markdown_lint_only", "markdown_files", "summary_json"}


class TestRemovedFlagsAreRejected:
    """--skip-tests and --verbose were parsed and discarded; both are gone.

    Deleting their old tests would only prove the flags are untested. These
    assert argparse actively rejects them, so reintroducing a parsed-and-ignored
    flag under either name fails here.
    """

    @pytest.mark.parametrize("flag", ["--skip-tests", "--verbose"])
    def test_parser_rejects_removed_flag(self, flag: str) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args([flag])
        assert exc.value.code == 2

    @pytest.mark.parametrize("flag", ["--skip-tests", "--verbose"])
    def test_main_exits_two_on_removed_flag(self, flag: str) -> None:
        """CLI exit code, not just the parser: ADR-035 reserves 2 for config."""
        with pytest.raises(SystemExit) as exc:
            main([flag])
        assert exc.value.code == 2

    def test_removed_flags_are_rejected_together(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--quick", "--skip-tests", "--verbose"])
        assert exc.value.code == 2

    def test_parsed_namespace_has_no_removed_destinations(self) -> None:
        """Edge: absent from the namespace, not merely absent from the CLI."""
        args = build_parser().parse_args([])
        assert not hasattr(args, "skip_tests")
        assert not hasattr(args, "verbose")

    def test_skip_tests_env_var_no_longer_feeds_the_parser(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SKIP_TESTS was the flag's env default; it must now be inert."""
        monkeypatch.setenv("SKIP_TESTS", "true")
        args = build_parser().parse_args([])
        assert not hasattr(args, "skip_tests")

    def test_quick_still_reads_its_env_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Positive control: the surviving env default still works."""
        monkeypatch.setenv("QUICK_MODE", "true")
        assert build_parser().parse_args([]).quick is True


def test_always_on_corpus_claims_skips_without_test_tree(tmp_path: Path) -> None:
    (tmp_path / ".github" / "instructions").mkdir(parents=True)
    missing_script_skip = validate_always_on_corpus_claims.__globals__["MissingScriptSkip"]

    with pytest.raises(missing_script_skip, match="no corpus claim test to run"):
        validate_always_on_corpus_claims(tmp_path)
