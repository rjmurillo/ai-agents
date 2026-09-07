"""Tests for shared validation subprocess behavior."""

from __future__ import annotations

import sys
from unittest.mock import patch

from scripts.validation import subprocess_runner
from scripts.validation.evidence import (
    REASON_DIFF_FAILED,
    REASON_TIMEOUT,
    REASON_TOOL_ABSENT,
)
from scripts.validation.subprocess_runner import classify_subprocess_failure


def test_subprocess_resolves_windows_command_shim() -> None:
    completed = subprocess_runner.subprocess.CompletedProcess(
        ["npx.cmd", "--version"], 0, "11.17.0\n", ""
    )
    with (
        patch.object(
            subprocess_runner,
            "resolve_executable",
            return_value=r"C:\Program Files\nodejs\npx.cmd",
        ) as resolver,
        patch.object(subprocess_runner.subprocess, "run", return_value=completed) as run,
    ):
        result = subprocess_runner._run_subprocess(["npx", "--version"])

    assert result == (0, "11.17.0\n", "")
    resolver.assert_called_once_with("npx", env=None)
    assert run.call_args.args[0] == [
        r"C:\Program Files\nodejs\npx.cmd",
        "--version",
    ]


def test_subprocess_preserves_explicit_executable_path() -> None:
    completed = subprocess_runner.subprocess.CompletedProcess(
        [sys.executable, "--version"], 0, "Python\n", ""
    )
    with (
        patch.object(subprocess_runner, "resolve_executable") as resolver,
        patch.object(subprocess_runner.subprocess, "run", return_value=completed) as run,
    ):
        result = subprocess_runner._run_subprocess([sys.executable, "--version"])

    assert result == (0, "Python\n", "")
    resolver.assert_not_called()
    assert run.call_args.args[0] == [sys.executable, "--version"]


class TestClassifySubprocessFailure:
    """A timed-out child and a child that exited non-zero are different findings.

    ``_run_subprocess`` reports a timeout and a missing executable as exit
    ``-1`` with a marker in stderr, and a real child failure as that child's own
    code. Collapsing all three into one reason code costs the reader the first
    diagnostic step, which is what the typed evidence contract exists to avoid
    (issue #5635).
    """

    def test_a_timeout_is_reported_as_a_timeout(self) -> None:
        """Positive: the sentinel exit plus the timeout marker."""
        reason = classify_subprocess_failure(
            -1, "Command timed out after 30s", default=REASON_DIFF_FAILED
        )

        assert reason == REASON_TIMEOUT

    def test_a_timeout_is_recognized_behind_partial_child_stderr(self) -> None:
        """Edge: issue #4955 prepends the child's partial stderr to the marker."""
        reason = classify_subprocess_failure(
            -1,
            "fatal: partial output from the child\nCommand timed out after 30s",
            default=REASON_DIFF_FAILED,
        )

        assert reason == REASON_TIMEOUT

    def test_a_missing_executable_is_reported_as_an_absent_tool(self) -> None:
        """Positive: the other sentinel path."""
        reason = classify_subprocess_failure(
            -1, "Command not found: git", default=REASON_DIFF_FAILED
        )

        assert reason == REASON_TOOL_ABSENT

    def test_a_real_child_failure_keeps_the_caller_s_reason(self) -> None:
        """Negative: only the caller knows what its child was doing."""
        reason = classify_subprocess_failure(
            128, "fatal: bad revision 'origin/main...HEAD'", default=REASON_DIFF_FAILED
        )

        assert reason == REASON_DIFF_FAILED

    def test_the_sentinel_exit_alone_keeps_the_caller_s_reason(self) -> None:
        """Edge: exit -1 with neither marker is not evidence of a timeout.

        NEGATIVE CONTROL: a classifier keyed on the exit code alone returns
        REASON_TIMEOUT here and mislabels an unrecognized failure.
        """
        reason = classify_subprocess_failure(-1, "", default=REASON_DIFF_FAILED)

        assert reason == REASON_DIFF_FAILED

    def test_the_marker_alone_keeps_the_caller_s_reason(self) -> None:
        """Edge: a child that printed the marker text and exited 1 is not a timeout.

        NEGATIVE CONTROL: a classifier keyed on the stderr text alone returns
        REASON_TIMEOUT here, letting a child's own output rename the finding.
        """
        reason = classify_subprocess_failure(
            1, "Command timed out after 30s", default=REASON_DIFF_FAILED
        )

        assert reason == REASON_DIFF_FAILED
