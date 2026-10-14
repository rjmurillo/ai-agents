"""Pre-push runs the tests pytest-testmon selects, best effort: the command shape.

Issue #6239, owner decision of 2026-10-09: the default pre-push pytest step runs
``pytest --testmon`` over ``tests/``. Nothing in the hook module imports the
repository's own import-graph selector. Sibling modules cover the run, the
partition exit codes, the seed fetch, and the dependency setup.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy
from tests.validation.pre_push_testmon_helpers import (
    default_environment,  # noqa: F401  (fixture, applied by usefixtures below)
    testmon,
)

pytestmark = pytest.mark.usefixtures("default_environment")

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_default_pre_push_resolves_to_the_testmon_commands(tmp_path: Path) -> None:
    assert git_hook_policy._resolve_pytest_commands(tmp_path) == testmon(tmp_path)


def test_every_testmon_command_selects_with_testmon_and_skips_integration(
    tmp_path: Path,
) -> None:
    for command in testmon(tmp_path):
        assert command[:3] == [sys.executable, "-m", "pytest"]
        assert "--testmon" in command
        assert any(arg.startswith("not integration") for arg in command)
        assert "--collect-only" not in command


def test_the_testmon_commands_are_the_full_suite_partitions_plus_the_flag(
    tmp_path: Path,
) -> None:
    """The serial safe-push and pr-autofix handling is kept, partition for partition."""
    full = git_hook_policy._pytest_commands(tmp_path)
    selected = testmon(tmp_path)
    assert len(selected) == len(full)
    for with_testmon, without in zip(selected, full, strict=True):
        flags = set(git_hook_policy._TESTMON_FLAGS)
        assert [arg for arg in with_testmon if arg not in flags] == without


def test_every_testmon_command_loads_the_scoped_sync_plugin(tmp_path: Path) -> None:
    """Without it a partition deletes a sibling's records (issue #6406)."""
    for command in testmon(tmp_path):
        assert "-pscripts.validation.testmon_scoped_sync" in command


def test_testmon_selection_survives_the_marker_filter(tmp_path: Path) -> None:
    """testmon 2.2.0 turns selection off under ``-m`` unless forceselect is passed.

    Without the flag the run reports "selection automatically deactivated
    because -m was used" and executes the whole suite on every push.
    """
    for command in testmon(tmp_path):
        assert any(arg.startswith("not integration") for arg in command)
        assert "--testmon-forceselect" in command


def test_the_bulk_testmon_command_uses_worksteal_over_tests(tmp_path: Path) -> None:
    bulk = testmon(tmp_path)[0]
    assert bulk[bulk.index("--dist") + 1] == "worksteal"
    assert "-n" in bulk
    assert str(tmp_path / "tests") in bulk


def test_the_serial_testmon_partitions_take_no_worker_pool(tmp_path: Path) -> None:
    _bulk, _mutation, safe_push, pr_autofix = testmon(tmp_path)
    for serial in (safe_push, pr_autofix):
        assert "-n" not in serial
        assert "--dist" not in serial


def test_testmon_never_runs_with_the_cacheprovider_disabled(tmp_path: Path) -> None:
    """``-p no:cacheprovider`` crashes testmon with KeyError 'lf'."""
    for command in testmon(tmp_path):
        assert "no:cacheprovider" not in " ".join(command)
