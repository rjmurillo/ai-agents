"""Every partition runs, and the exit code is the worst one (issue #6239).

Stopping at the first failure left later partitions unrecorded in
``.testmondata``, so the next push re-ran them all.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy
from tests.validation.pre_push_testmon_helpers import (
    default_environment,  # noqa: F401  (fixture, applied by usefixtures below)
    testmon,
)

pytestmark = pytest.mark.usefixtures("default_environment")

REPO_ROOT = Path(__file__).resolve().parents[2]


def _record_codes(monkeypatch: pytest.MonkeyPatch, codes: list[int]) -> list[list[str]]:
    """Return partition argv lists; each call exits with the next code."""
    seen: list[list[str]] = []
    pending = iter(codes)

    def fake(command: list[str], *_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        seen.append(list(command))
        return subprocess.CompletedProcess(command, next(pending), "", "")

    monkeypatch.setattr(git_hook_policy, "_run_command", fake)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)
    return seen


def test_a_failing_first_partition_still_runs_the_others(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every partition must record its tests, or the next push re-runs them all."""
    seen = _record_codes(monkeypatch, [1, 0, 0, 0])
    assert git_hook_policy.run_pytest(tmp_path) == 1
    assert seen == testmon(tmp_path)


@pytest.mark.parametrize(
    ("codes", "expected"),
    [
        ([0, 0, 0, 0], 0),
        ([1, 0, 0, 0], 1),
        ([0, 0, 1, 0], 1),
        ([1, 2, 0, 1], 2),
        ([1, 4, 2, 0], 4),
        # A signal-killed pytest reports a negative code (-9 is SIGKILL). It is
        # a failure, not a pass: max(0, -9) is 0 and would let the push through.
        ([-9, 0, 0, 0], 1),
        ([0, 0, 0, -11], 1),
        ([-9, 2, 0, 0], 2),
    ],
)
def test_the_exit_code_is_the_worst_partition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, codes: list[int], expected: int
) -> None:
    _record_codes(monkeypatch, codes)
    assert git_hook_policy.run_pytest(tmp_path) == expected


def test_a_later_failure_is_not_hidden_by_a_passing_last_partition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _record_codes(monkeypatch, [0, 1, 0, 0])
    assert git_hook_policy.run_pytest(tmp_path) == 1


def test_the_full_suite_opt_in_also_runs_every_partition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    # One worker cannot feed two pools, so the partitions run in the order listed.
    monkeypatch.setenv(git_hook_policy.PYTEST_WORKERS_ENV, "1")
    seen = _record_codes(monkeypatch, [1, 0, 0, 0])
    assert git_hook_policy.run_pytest(tmp_path) == 1
    assert seen == git_hook_policy._pytest_commands(tmp_path)
