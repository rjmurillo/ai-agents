"""The split groups share one pool and one restored durations map.

Issue #6239 acceptance criteria covered here:

- AC2: the parallel legs are duration-balanced split groups over one pool.
"""

from __future__ import annotations

import pytest

from scripts.ci import run_pytest_partition as mod

_SPLIT_PARTITIONS = ("split-1", "split-2", "split-3", "split-4")

_POOL_EXCLUDED = {
    "tests/test_ai_review.py",
    "tests/test_verdict.py",
    "tests/test_quality_gate.py",
    "tests/skills/github/test_wait_for_unresolved_zero.py",
    "tests/test_safe_push_pr_branch.py",
    "tests/test_mutation_workspace_signals.py",
    "tests/test_pr_autofix_late_live_state_gate.py",
}


def _flag_value(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


@pytest.mark.parametrize("index", range(1, 5))
def test_split_group_flags(index: int) -> None:
    """AC2: group i of N runs the shared pool by recorded duration."""
    args = mod._PARTITION_FULL_ARGS[f"split-{index}"]
    assert _flag_value(args, "--splits") == "4"
    assert _flag_value(args, "--group") == str(index)
    assert _flag_value(args, "--splitting-algorithm") == "duration_based_chunks"
    assert _flag_value(args, "--durations-path") == f"artifacts/durations-split-{index}.json"
    assert args[-1] == "tests/"


def test_split_groups_differ_only_in_the_group_number() -> None:
    """AC2: one pool, so no group can leave a file out or take it twice."""

    def without_group_and_leg_file(args: list[str]) -> list[str]:
        for flag in ("--group", "--durations-path"):
            position = args.index(flag)
            args = args[:position] + args[position + 2 :]
        return args

    shapes = {
        tuple(without_group_and_leg_file(mod._PARTITION_FULL_ARGS[n])) for n in _SPLIT_PARTITIONS
    }
    assert len(shapes) == 1


@pytest.mark.parametrize("partition", _SPLIT_PARTITIONS)
def test_split_groups_ignore_exactly_the_dedicated_and_pinned_files(partition: str) -> None:
    args = mod._PARTITION_FULL_ARGS[partition]
    ignored = {a.removeprefix("--ignore=") for a in args if a.startswith("--ignore=")}
    assert ignored == _POOL_EXCLUDED
    assert not [a for a in args if a.startswith("--ignore-glob")]


@pytest.mark.parametrize("partition", _SPLIT_PARTITIONS)
def test_split_legs_store_only_their_own_timings(partition: str) -> None:
    """--clean-durations keeps a leg file to that leg's tests, so the union is fresh."""
    args = mod._PARTITION_FULL_ARGS[partition]
    assert "--store-durations" in args
    assert "--clean-durations" in args


def test_each_split_leg_stores_to_its_own_path() -> None:
    """Shared paths would let one leg's upload overwrite another's timings."""
    paths = [
        _flag_value(mod._PARTITION_FULL_ARGS[n], "--durations-path") for n in _SPLIT_PARTITIONS
    ]
    assert len(set(paths)) == len(paths) == 4


@pytest.mark.parametrize("partition", _SPLIT_PARTITIONS)
def test_no_leg_stores_over_the_restored_file(partition: str) -> None:
    args = mod._PARTITION_FULL_ARGS[partition]
    assert _flag_value(args, "--durations-path") != mod.DURATIONS_RESTORE_PATH


def test_dedicated_legs_neither_read_nor_store_timings() -> None:
    for name in ("safe-push", "pr-autofix"):
        assert "--durations-path" not in mod._PARTITION_FULL_ARGS[name]
        assert "--store-durations" not in mod._PARTITION_FULL_ARGS[name]


def test_dedicated_legs_run_only_their_files() -> None:
    assert mod._PARTITION_FULL_ARGS["safe-push"] == [
        "tests/test_safe_push_pr_branch.py",
        "tests/test_mutation_workspace_signals.py",
    ]
    assert mod._PARTITION_FULL_ARGS["pr-autofix"] == [
        "tests/test_pr_autofix_late_live_state_gate.py"
    ]
