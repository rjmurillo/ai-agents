"""Tests for scripts/ci/spec_coverage_verdict.py (issue #6182)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci import spec_coverage_verdict as verdict_module
from scripts.ci.spec_coverage_verdict import (
    ACCEPTANCE_HEADING,
    EXIT_CONFIG,
    EXIT_FAIL,
    EXIT_OK,
    decide,
    main,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "spec_coverage_verdict.py"

ALL_CHECKED = "## Acceptance criteria\n\n- [x] one\n- [X] two\n"
ONE_UNCHECKED = "## Acceptance criteria\n\n- [x] one\n- [ ] two\n- [ ] three\n"
NUMBERED_ONLY = "## Acceptance criteria\n\n1. one\n2. two\n"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "HAS_SPECS", "PR_BODY", "EVENT_NAME", "PR_NUMBER",
        "GITHUB_REPOSITORY", "GITHUB_STEP_SUMMARY",
    ):
        monkeypatch.delenv(name, raising=False)


class TestDecide:
    def test_no_spec_passes_with_any_body(self) -> None:
        assert decide(False, "").passed
        assert decide(False, ONE_UNCHECKED).passed

    def test_spec_without_section_fails_and_names_heading(self) -> None:
        result = decide(True, "Just prose, no list.")
        assert not result.passed
        assert ACCEPTANCE_HEADING in result.reason

    def test_spec_with_empty_body_fails(self) -> None:
        assert not decide(True, "").passed

    def test_numbered_list_is_not_a_checkbox_section(self) -> None:
        result = decide(True, NUMBERED_ONLY)
        assert not result.passed
        assert ACCEPTANCE_HEADING in result.reason

    def test_unchecked_items_are_listed(self) -> None:
        result = decide(True, ONE_UNCHECKED)
        assert not result.passed
        assert result.unchecked == ["two", "three"]
        assert "2 of 3" in result.reason

    def test_all_checked_passes(self) -> None:
        result = decide(True, ALL_CHECKED)
        assert result.passed
        assert result.unchecked == []

    def test_repeat_calls_return_equal_verdicts(self) -> None:
        assert decide(True, ONE_UNCHECKED) == decide(True, ONE_UNCHECKED)


class TestRun:
    def test_no_spec_exits_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HAS_SPECS", "false")
        assert run() == EXIT_OK

    def test_has_specs_is_case_and_space_tolerant(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HAS_SPECS", " TRUE ")
        monkeypatch.setenv("PR_BODY", ALL_CHECKED)
        assert run() == EXIT_OK

    @pytest.mark.parametrize("raw", ["", "yes", "1", "null"])
    def test_bad_has_specs_is_config_error(
        self, monkeypatch: pytest.MonkeyPatch, raw: str
    ) -> None:
        monkeypatch.setenv("HAS_SPECS", raw)
        assert run() == EXIT_CONFIG

    def test_unset_has_specs_is_config_error(self) -> None:
        assert run() == EXIT_CONFIG

    def test_missing_section_exits_fail_with_error_annotation(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("PR_BODY", "no list")
        assert run() == EXIT_FAIL
        out = capsys.readouterr().out
        assert "::error::" in out
        assert ACCEPTANCE_HEADING in out

    def test_unchecked_exits_fail_and_lists_each(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("PR_BODY", ONE_UNCHECKED)
        assert run() == EXIT_FAIL
        out = capsys.readouterr().out
        assert "::error::Unchecked acceptance criterion: two" in out
        assert "::error::Unchecked acceptance criterion: three" in out

    def test_all_checked_exits_ok_without_error_annotation(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("PR_BODY", ALL_CHECKED)
        assert run() == EXIT_OK
        assert "::error::" not in capsys.readouterr().out

    def test_repeat_runs_return_same_exit_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("PR_BODY", ONE_UNCHECKED)
        assert run() == run() == EXIT_FAIL

    def test_summary_written_on_fail(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("PR_BODY", ONE_UNCHECKED)
        assert run() == EXIT_FAIL
        text = summary.read_text(encoding="utf-8")
        assert "Validate Spec Coverage: FAIL" in text
        assert "- [ ] two" in text
        assert "- [ ] three" in text

    def test_summary_written_on_pass(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.setenv("HAS_SPECS", "false")
        assert run() == EXIT_OK
        assert "Validate Spec Coverage: PASS" in summary.read_text(encoding="utf-8")

    def test_pull_request_event_never_calls_gh(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("EVENT_NAME", "pull_request")
        with patch.object(verdict_module.subprocess, "run") as mock_run:
            assert run() == EXIT_FAIL
        mock_run.assert_not_called()


class TestDispatchFetch:
    def _env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("EVENT_NAME", "workflow_dispatch")
        monkeypatch.setenv("PR_NUMBER", "42")
        monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")

    def test_fetches_body_when_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._env(monkeypatch)
        done = subprocess.CompletedProcess([], 0, stdout=ALL_CHECKED + "\n", stderr="")
        with patch.object(verdict_module.subprocess, "run", return_value=done) as mock_run:
            assert run() == EXIT_OK
        assert mock_run.call_args.args[0][:4] == ["gh", "pr", "view", "42"]

    def test_skips_fetch_when_body_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._env(monkeypatch)
        monkeypatch.setenv("PR_BODY", ALL_CHECKED)
        with patch.object(verdict_module.subprocess, "run") as mock_run:
            assert run() == EXIT_OK
        mock_run.assert_not_called()

    def test_nonzero_gh_exit_is_config_error(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._env(monkeypatch)
        failed = subprocess.CompletedProcess([], 1, stdout="", stderr="boom")
        with patch.object(verdict_module.subprocess, "run", return_value=failed):
            assert run() == EXIT_CONFIG
        assert "gh pr view failed" in capsys.readouterr().err

    def test_gh_launch_failure_is_config_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._env(monkeypatch)
        with patch.object(verdict_module.subprocess, "run", side_effect=OSError("no gh")):
            assert run() == EXIT_CONFIG

    def test_gh_timeout_is_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._env(monkeypatch)
        timeout = subprocess.TimeoutExpired(cmd="gh", timeout=1)
        with patch.object(verdict_module.subprocess, "run", side_effect=timeout):
            assert run() == EXIT_CONFIG

    @pytest.mark.parametrize("missing", ["PR_NUMBER", "GITHUB_REPOSITORY"])
    def test_missing_fetch_inputs_is_config_error(
        self, monkeypatch: pytest.MonkeyPatch, missing: str
    ) -> None:
        self._env(monkeypatch)
        monkeypatch.delenv(missing)
        with patch.object(verdict_module.subprocess, "run") as mock_run:
            assert run() == EXIT_CONFIG
        mock_run.assert_not_called()


class TestCli:
    def test_main_returns_fail_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("PR_BODY", ONE_UNCHECKED)
        assert main() == EXIT_FAIL

    def test_main_returns_config_code(self) -> None:
        assert main() == EXIT_CONFIG

    @pytest.mark.parametrize(
        ("has_specs", "body", "code"),
        [("false", "", 0), ("true", ONE_UNCHECKED, 1), ("true", ALL_CHECKED, 0), ("x", "", 2)],
    )
    def test_script_runs_under_isolated_python_from_other_cwd(
        self, tmp_path: Path, has_specs: str, body: str, code: int
    ) -> None:
        """Bare-interpreter check: the script imports only the standard library."""
        env = {"HAS_SPECS": has_specs, "PR_BODY": body, "PATH": "/usr/bin:/bin"}
        proc = subprocess.run(
            [sys.executable, "-I", str(SCRIPT)],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == code, proc.stderr
        assert "ModuleNotFoundError" not in proc.stderr
