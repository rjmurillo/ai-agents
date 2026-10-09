"""The pre-push notice and the opt-in full suite agree with what CI runs.

Issue #6239 acceptance criteria covered here:

- AC2: every pytest CI leg runs its full share on every event, so the notice a
  contributor reads at push time must say so and must not describe the retired
  paths-filter behavior.
- AC5: the opt-in full suite runs the same dedicated serial files as the CI
  runner's dedicated legs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci import run_pytest_partition
from scripts.validation import git_hook_policy


def test_the_notice_says_ci_runs_every_leg_on_every_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git_hook_policy._collection_stand_in(tmp_path)
    notice = capsys.readouterr().err
    assert "every pytest leg in\n  full on every push, pull request, and merge-queue event" in notice
    assert "paths filter" not in notice


def test_the_opt_in_full_suite_runs_the_ci_dedicated_files(tmp_path: Path) -> None:
    commands = git_hook_policy._pytest_commands(tmp_path)
    named = {
        Path(arg).relative_to(tmp_path).as_posix()
        for command in commands
        for arg in command
        if arg.startswith(str(tmp_path)) and arg.endswith(".py")
    }
    dedicated = run_pytest_partition._SAFE_PUSH_TESTS | run_pytest_partition._PR_AUTOFIX_TESTS
    assert dedicated <= named
