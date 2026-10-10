"""Running the testmon selection: environment, exit codes, and budget (issue #6239)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import git_hook_policy
from tests.validation.pre_push_testmon_helpers import (
    default_environment,  # noqa: F401  (fixture, applied by usefixtures below)
    record_runs,
)

pytestmark = pytest.mark.usefixtures("default_environment")


def _captured_children(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[dict[str, Any]]:
    """Run the hook against a stub boundary; return each child's argv, env, and timeout."""
    children: list[dict[str, Any]] = []

    def fake(command: list[str], _root: object, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        children.append({"command": command, **kwargs})
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    monkeypatch.setattr(git_hook_policy, "_run_command", fake)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)
    assert git_hook_policy.run_pytest(tmp_path) == 0
    return children


@pytest.mark.parametrize(
    ("opt_in", "uses_testmon", "core"), [(False, True, "ctrace"), (True, False, "sysmon")]
)
def test_only_the_testmon_path_forces_the_ctrace_coverage_core(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, opt_in: bool, uses_testmon: bool, core: str
) -> None:
    """On Python 3.14 coverage defaults to sysmon, which under-records for testmon."""
    monkeypatch.setenv("COVERAGE_CORE", "sysmon")
    if opt_in:
        monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    for child in _captured_children(monkeypatch, tmp_path):
        assert ("--testmon" in child["command"]) is uses_testmon
        assert child["process_env"]["COVERAGE_CORE"] == core


def test_default_pre_push_asks_git_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    record_runs(monkeypatch)
    monkeypatch.setattr(
        git_hook_policy,
        "_run_git",
        lambda *_a, **_k: pytest.fail("pre-push pytest must not ask git for a diff"),
    )
    assert git_hook_policy.run_pytest(tmp_path) == 0


@pytest.mark.parametrize("exit_code", [1, 2, 4])
def test_a_failing_testmon_run_blocks_the_push(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, exit_code: int
) -> None:
    record_runs(monkeypatch, returncode=exit_code)
    assert git_hook_policy.run_pytest(tmp_path) == exit_code


def test_the_testmon_budget_is_the_suite_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The first run builds the database over the whole suite, so it needs the full budget."""
    first = _captured_children(monkeypatch, tmp_path)[0]["timeout_seconds"]
    assert git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS - 5 < first
    assert first <= git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
