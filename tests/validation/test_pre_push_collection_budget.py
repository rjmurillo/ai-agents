"""Pre-push pytest time budgets and timeout reporting.

Issue #6239 AC5: collection gets its own short ceiling, and a pytest crash is
not reported as a timeout.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy
from tests.validation.pre_push_collection_helpers import (
    collection,
    default_environment,  # noqa: F401  (fixture, applied by usefixtures below)
    record_runs,
)

pytestmark = pytest.mark.usefixtures("default_environment")


def test_collection_gets_the_collection_budget_not_the_suite_budget(tmp_path: Path) -> None:
    """A collection hang must not be able to block a push for 29 minutes."""
    assert (
        git_hook_policy._pytest_budget_seconds(collection(tmp_path))
        == git_hook_policy.TEST_COLLECTION_TIMEOUT_SECONDS
    )
    assert (
        git_hook_policy.TEST_COLLECTION_TIMEOUT_SECONDS < git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    )


def test_executing_commands_keep_the_suite_budget(tmp_path: Path) -> None:
    assert (
        git_hook_policy._pytest_budget_seconds(git_hook_policy._pytest_commands(tmp_path))
        == git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    )


def test_a_pytest_internal_error_is_not_reported_as_a_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 3 is overloaded: pytest INTERNALERROR and ``_run_command``'s timeout kill.

    ``run_pytest`` reads the timeout marker ``_run_command`` appends, not the
    bare code, so a genuine pytest crash is not announced as a budget problem.
    """
    record_runs(monkeypatch, returncode=3, stderr="INTERNALERROR> Traceback\n")
    assert git_hook_policy.run_pytest(tmp_path) == 3
    err = capsys.readouterr().err
    assert "timed out" not in err
    assert "budget" not in err


def test_a_collection_timeout_names_the_collection_ceiling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The timeout message is all a developer whose push just died has to go on."""
    monkeypatch.setattr(
        git_hook_policy,
        "_run_command",
        lambda *_a, **kw: subprocess.CompletedProcess(
            ["pytest"],
            3,
            "",
            git_hook_policy._timeout_message(["pytest"], kw["timeout_seconds"]),
        ),
    )
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)
    assert git_hook_policy.run_pytest(tmp_path) == 3
    err = capsys.readouterr().err
    assert str(git_hook_policy.TEST_COLLECTION_TIMEOUT_SECONDS) in err
    assert str(git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS) not in err
