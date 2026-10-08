"""The partition table: names, parallel flags, and classification.

Issue #6239 acceptance criteria covered here:

- AC2: every pytest CI leg runs its full share on every event.
- AC4: the parallel legs are duration-balanced split groups over one pool.
"""

from __future__ import annotations

import pytest

from scripts.ci import run_pytest_partition as mod

_SPLIT_PARTITIONS = ("split-1", "split-2", "split-3", "split-4")


def test_split_count_is_four_and_names_follow_it() -> None:
    assert mod.SPLIT_COUNT == 4
    assert mod.split_names() == list(_SPLIT_PARTITIONS)


def test_distribution_mode_is_loadfile() -> None:
    assert mod.PYTEST_DIST_MODE == "loadfile"
    assert mod._PARALLEL == ["-n", "auto", "--dist", mod.PYTEST_DIST_MODE]


@pytest.mark.parametrize("partition", sorted(mod._PARALLEL_PARTITIONS))
def test_parallel_partitions_start_with_the_parallel_flags(partition: str) -> None:
    assert mod._PARTITION_FULL_ARGS[partition][:4] == mod._PARALLEL


@pytest.mark.parametrize("partition", ["safe-push", "pr-autofix"])
def test_serial_partitions_carry_no_parallel_flags(partition: str) -> None:
    assert "-n" not in mod._PARTITION_FULL_ARGS[partition]
    assert "--dist" not in mod._PARTITION_FULL_ARGS[partition]


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("tests/test_leaf.py", "split"),
        ("tests/ci/test_thing.py", "split"),
        ("tests/validation/test_thing.py", "split"),
        ("tests/mutation/test_x.py", "split"),
        ("tests/skills/github/test_wait_for_unresolved_zero.py", None),
        ("tests/test_safe_push_pr_branch.py", "safe-push"),
        ("tests/test_pr_autofix_late_live_state_gate.py", "pr-autofix"),
        ("tests/test_verdict.py", None),
    ],
)
def test_classify_partition(rel: str, expected: str | None) -> None:
    assert mod.classify_partition(rel) == expected
