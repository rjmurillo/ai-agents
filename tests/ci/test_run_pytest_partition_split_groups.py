"""The split groups share one pool and one restored durations map.

Issue #6239 acceptance criteria covered here:

- AC2: the parallel legs are duration-balanced split groups over one pool.
"""

from __future__ import annotations

import pytest
from pytest_split.algorithms import Algorithms

from scripts.ci import run_pytest_partition as mod

_SPLIT_PARTITIONS = ("split-1", "split-2", "split-3", "split-4", "split-5")

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


@pytest.mark.parametrize("index", range(1, 6))
def test_split_group_flags(index: int) -> None:
    """AC2: group i of N runs the shared pool by recorded duration."""
    args = mod._PARTITION_FULL_ARGS[f"split-{index}"]
    assert _flag_value(args, "--splits") == "5"
    assert _flag_value(args, "--group") == str(index)
    assert _flag_value(args, "--splitting-algorithm") == "least_duration"
    assert _flag_value(args, "--durations-path") == f"artifacts/durations-split-{index}.json"
    assert args[-1] == "tests/"


def test_split_groups_differ_only_in_the_group_number() -> None:
    """AC2: one pool, so no group can leave a file out or take it twice."""

    def without_group(args: list[str]) -> list[str]:
        for flag in ("--group", "--durations-path"):
            position = args.index(flag)
            args = args[:position] + args[position + 2 :]
        return args

    shapes = {tuple(without_group(mod._PARTITION_FULL_ARGS[n])) for n in _SPLIT_PARTITIONS}
    assert len(shapes) == 1


@pytest.mark.parametrize("partition", _SPLIT_PARTITIONS)
def test_split_groups_ignore_exactly_the_dedicated_and_pinned_files(partition: str) -> None:
    args = mod._PARTITION_FULL_ARGS[partition]
    ignored = {a.removeprefix("--ignore=") for a in args if a.startswith("--ignore=")}
    assert ignored == _POOL_EXCLUDED
    assert not [a for a in args if a.startswith("--ignore-glob")]


def test_each_split_leg_stores_to_its_own_path() -> None:
    args = [mod._PARTITION_FULL_ARGS[n] for n in _SPLIT_PARTITIONS]
    paths = {_flag_value(a, "--durations-path") for a in args}
    assert len(paths) == 5


def test_dedicated_legs_run_only_their_files() -> None:
    assert mod._PARTITION_FULL_ARGS["safe-push"] == [
        "tests/test_safe_push_pr_branch.py",
        "tests/test_mutation_workspace_signals.py",
    ]
    assert mod._PARTITION_FULL_ARGS["pr-autofix"] == [
        "tests/test_pr_autofix_late_live_state_gate.py"
    ]


class _Item:
    """The one attribute pytest-split reads from a collected item."""

    def __init__(self, nodeid: str) -> None:
        self.nodeid = nodeid

    def __str__(self) -> str:
        return self.nodeid


def test_adjacent_slow_tests_land_on_different_legs() -> None:
    """Issue #6828: slow tests that sort together must not share one leg.

    Mirrors the tests/ci/ cluster: three long tests side by side, then many
    short ones. Contiguous chunks put all three on split-1 and pushed it past
    the job timeout. The configured algorithm must spread them out.
    """
    slow = {"tests/ci/test_a.py::t": 180.0, "tests/ci/test_b.py::t": 116.0}
    slow["tests/ci/test_c.py::t"] = 71.0
    fast = {f"tests/z/test_{i:03}.py::t": 2.0 for i in range(400)}
    durations = {**slow, **fast}
    items = [_Item(node_id) for node_id in durations]

    groups = Algorithms[mod.SPLITTING_ALGORITHM].value(mod.SPLIT_COUNT, items, durations)

    homes = {
        index
        for index, group in enumerate(groups)
        for item in group.selected
        if item.nodeid in slow
    }
    assert len(homes) == len(slow)
    totals = [group.duration for group in groups]
    assert max(totals) - min(totals) <= max(slow.values())
