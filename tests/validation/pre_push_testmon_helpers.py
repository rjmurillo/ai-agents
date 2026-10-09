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


class RecordedRuns:
    """The argv lists and child environments the hook handed to the subprocess boundary."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.envs: list[dict[str, str]] = []


def record_runs(
    monkeypatch: pytest.MonkeyPatch, returncode: int = 0, stderr: str = ""
) -> RecordedRuns:
    """Replace the subprocess boundary and return what it receives."""
    seen = RecordedRuns()

    def fake(
        command: list[str], _root: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        seen.commands.append(list(command))
        env = kwargs.get("process_env")
        seen.envs.append(dict(env) if isinstance(env, dict) else {})
        return subprocess.CompletedProcess(command, returncode, "", stderr)

    monkeypatch.setattr(git_hook_policy, "_run_command", fake)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)
    return seen
