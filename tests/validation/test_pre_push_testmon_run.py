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


def test_the_testmon_budget_is_the_selection_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Issue #6200: the selection gets 180s, not the 780s of a whole-suite run."""
    first = _captured_children(monkeypatch, tmp_path)[0]["timeout_seconds"]
    assert git_hook_policy.PRE_PUSH_SELECTION_TIMEOUT_SECONDS - 5 < first
    assert first <= git_hook_policy.PRE_PUSH_SELECTION_TIMEOUT_SECONDS


def test_the_selection_budget_plus_the_recorded_earlier_stages_is_under_the_target() -> None:
    """Arithmetic over a recorded measurement, not a live check of sibling jobs.

    ADR-104 targets 300s per push.
    The stages before the expensive group took 26s in-hook (2026-10-13), so the
    push worst case is those stages plus the longest job in the group. Pytest
    is that job once it passes pre-pr-validation's 170s.
    """
    stages_before_the_group = 26
    worst_push = stages_before_the_group + git_hook_policy.PRE_PUSH_SELECTION_TIMEOUT_SECONDS
    assert worst_push <= 300
    assert git_hook_policy.PRE_PUSH_SELECTION_TIMEOUT_SECONDS < (
        git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    )


def test_the_seed_budget_applies_only_to_the_seed_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The seed run takes about 30 minutes, so it needs its own budget (issue #6239).

    The override is read only when the seed job's marker is set, so a developer
    who exports it by accident keeps the suite budget.
    """
    monkeypatch.setenv(git_hook_policy.TESTMON_SEED_BUDGET_ENV, "3300")
    ignored = _captured_children(monkeypatch, tmp_path)[0]["timeout_seconds"]
    assert ignored <= git_hook_policy.PRE_PUSH_SELECTION_TIMEOUT_SECONDS
    monkeypatch.setenv(git_hook_policy.TESTMON_NO_SEED_ENV, "1")
    seeded = _captured_children(monkeypatch, tmp_path)[0]["timeout_seconds"]
    assert 3290 < seeded <= 3300


@pytest.mark.parametrize("value", ["0", "-5", "abc", "1.5", " "])
def test_a_bad_seed_budget_is_a_config_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    monkeypatch.setenv(git_hook_policy.TESTMON_NO_SEED_ENV, "1")
    monkeypatch.setenv(git_hook_policy.TESTMON_SEED_BUDGET_ENV, value)
    seen = record_runs(monkeypatch)
    assert git_hook_policy.run_pytest(tmp_path) == 2
    assert seen == []


def test_the_seed_budget_is_not_handed_to_pytest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(git_hook_policy.TESTMON_NO_SEED_ENV, "1")
    monkeypatch.setenv(git_hook_policy.TESTMON_SEED_BUDGET_ENV, "3300")
    for child in _captured_children(monkeypatch, tmp_path):
        assert git_hook_policy.TESTMON_SEED_BUDGET_ENV not in child["process_env"]
