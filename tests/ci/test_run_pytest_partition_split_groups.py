"""The split groups share one pool and one durations file.

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
    assert _flag_value(args, "--durations-path") == "tests/.test_durations"
    assert args[-1] == "tests/"


def test_split_groups_differ_only_in_the_group_number() -> None:
    """AC2: one pool, so no group can leave a file out or take it twice."""

    def without_group(args: list[str]) -> list[str]:
        position = args.index("--group")
        return args[:position] + args[position + 2 :]

    shapes = {tuple(without_group(mod._PARTITION_FULL_ARGS[n])) for n in _SPLIT_PARTITIONS}
    assert len(shapes) == 1


@pytest.mark.parametrize("partition", _SPLIT_PARTITIONS)
def test_split_groups_ignore_exactly_the_dedicated_and_pinned_files(partition: str) -> None:
    args = mod._PARTITION_FULL_ARGS[partition]
    ignored = {a.removeprefix("--ignore=") for a in args if a.startswith("--ignore=")}
    assert ignored == _POOL_EXCLUDED
    assert not [a for a in args if a.startswith("--ignore-glob")]


def test_durations_file_lives_beside_the_tests() -> None:
    assert mod.DURATIONS_PATH == "tests/.test_durations"


def test_dedicated_legs_run_only_their_files() -> None:
    assert mod._PARTITION_FULL_ARGS["safe-push"] == [
        "tests/test_safe_push_pr_branch.py",
        "tests/test_mutation_workspace_signals.py",
    ]
    assert mod._PARTITION_FULL_ARGS["pr-autofix"] == [
        "tests/test_pr_autofix_late_live_state_gate.py"
    ]
