"""Each split leg stores its own timings, never over the restored file."""

from __future__ import annotations

import pytest

from scripts.ci import run_pytest_partition as mod

_SPLIT_PARTITIONS = ("split-1", "split-2", "split-3", "split-4")


def _path_flag(partition: str) -> str:
    args = mod._PARTITION_FULL_ARGS[partition]
    return args[args.index("--durations-path") + 1]


@pytest.mark.parametrize("partition", _SPLIT_PARTITIONS)
def test_split_legs_store_only_their_own_timings(partition: str) -> None:
    """--clean-durations keeps a leg file to that leg's tests, so the union is fresh."""
    args = mod._PARTITION_FULL_ARGS[partition]
    assert "--store-durations" in args
    assert "--clean-durations" in args


@pytest.mark.parametrize("partition", _SPLIT_PARTITIONS)
def test_no_leg_stores_over_the_restored_file(partition: str) -> None:
    assert _path_flag(partition) != mod.DURATIONS_RESTORE_PATH


@pytest.mark.parametrize("partition", ["safe-push", "pr-autofix"])
def test_dedicated_legs_neither_read_nor_store_timings(partition: str) -> None:
    args = mod._PARTITION_FULL_ARGS[partition]
    assert "--durations-path" not in args
    assert "--store-durations" not in args
