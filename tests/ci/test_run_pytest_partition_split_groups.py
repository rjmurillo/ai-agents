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
    assert _flag_value(args, "--splitting-algorithm") == "least_duration"
    assert _flag_value(args, "--durations-path") == f"artifacts/durations-split-{index}.json"
    assert args[-1] == "tests/"


def _worst_leg_over_mean(algorithm: str, weights: list[float]) -> float:
    """Assign synthetic tests with pytest-split's own algorithm; return max over mean."""
    from types import SimpleNamespace

    from pytest_split.algorithms import Algorithms

    items = [SimpleNamespace(nodeid=f"tests/t_{i:04d}.py::test") for i in range(len(weights))]
    durations = {item.nodeid: weight for item, weight in zip(items, weights, strict=True)}
    groups = Algorithms[algorithm].value(mod.SPLIT_COUNT, items, durations)
    sums = [sum(durations[item.nodeid] for item in group.selected) for group in groups]
    return max(sums) / (sum(sums) / len(sums))


def test_split_algorithm_keeps_the_worst_leg_near_the_mean() -> None:
    """Issue #6751: a heavy contiguous clump must not pile onto one leg.

    Three 150 s tests sit at the head of the collection order, ahead of 850 one
    second tests. Contiguous chunks put two heavy tests in group 1 and leave the
    rest light, so the worst leg is far over the mean. The configured algorithm
    stays within 5 percent.
    """
    weights = [150.0] * 3 + [1.0] * 850
    assert _worst_leg_over_mean("duration_based_chunks", weights) > 1.3
    assert _worst_leg_over_mean(mod.SPLITTING_ALGORITHM, weights) <= 1.05


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
    assert len(paths) == 4


def test_dedicated_legs_run_only_their_files() -> None:
    assert mod._PARTITION_FULL_ARGS["safe-push"] == [
        "tests/test_safe_push_pr_branch.py",
        "tests/test_mutation_workspace_signals.py",
    ]
    assert mod._PARTITION_FULL_ARGS["pr-autofix"] == [
        "tests/test_pr_autofix_late_live_state_gate.py"
    ]
