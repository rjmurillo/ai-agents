"""Shared fixtures and helpers for the pre-push testmon tests (issue #6239).

Imported by test_pre_push_*.py. The name does not match `test_*.py`, so pytest
never walks it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy

CONFIG_ERROR_EXIT = 2


def testmon(tmp_path: Path) -> list[list[str]]:
    return git_hook_policy._testmon_commands(tmp_path)


@pytest.fixture
def default_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.delenv(git_hook_policy.PYTEST_WORKERS_ENV, raising=False)
    monkeypatch.delenv(git_hook_policy.PYTEST_WORKER_CAP_ENV, raising=False)
    monkeypatch.delenv("COVERAGE_CORE", raising=False)
    monkeypatch.delenv(git_hook_policy.TESTMON_NO_SEED_ENV, raising=False)
    # No test may reach the network: the seed fetch is stubbed to "no seed".
    monkeypatch.setattr(
        git_hook_policy.testmon_seed,
        "fetch_seed",
        lambda _root, **_kw: git_hook_policy.testmon_seed.SeedResult(False, "stubbed in tests"),
    )


def record_runs(
    monkeypatch: pytest.MonkeyPatch, returncode: int = 0, stderr: str = ""
) -> list[list[str]]:
    """Replace the subprocess boundary and return the argv list it receives."""
    seen: list[list[str]] = []

    def fake(command: list[str], *_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        seen.append(list(command))
        return subprocess.CompletedProcess(command, returncode, "", stderr)

    monkeypatch.setattr(git_hook_policy, "_run_command", fake)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)
    return seen
