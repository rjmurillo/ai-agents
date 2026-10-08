"""Every test file runs in exactly one pytest partition kind (issues #4854, #6239)."""

from __future__ import annotations

from pathlib import Path

from scripts.ci import run_pytest_partition
from tests.workflows.pytest_partition_helpers import selects, tracked_tests


class TestPartitionsCoverEveryTestFileOnce:
    """Each test file runs in exactly one partition, or in a named pin step."""

    def test_every_test_file_has_exactly_one_owner(self) -> None:
        files = sorted(f for f in tracked_tests() if Path(f).name.startswith("test_"))
        assert files, "no tracked test files found"
        full_args = run_pytest_partition._PARTITION_FULL_ARGS
        # The split groups share one pool; which group runs a file depends on
        # the durations file, so ownership is by kind: the pool, or a dedicated leg.
        kinds = {
            ("split" if name in run_pytest_partition.split_names() else name): args
            for name, args in full_args.items()
        }
        unowned: list[str] = []
        doubled: list[str] = []
        for rel in files:
            owners = [kind for kind, args in kinds.items() if selects(args, rel)]
            if not owners:
                unowned.append(rel)
            elif len(owners) > 1:
                doubled.append(f"{rel}: {owners}")
        assert not doubled, doubled
        assert set(unowned) <= run_pytest_partition._UNPARTITIONED_TESTS
