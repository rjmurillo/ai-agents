"""Split groups differ in `--group` only (issue #6239)."""

from __future__ import annotations

from scripts.ci import run_pytest_partition
from tests.workflows.pytest_partition_helpers import selects, tracked_tests


class TestSplitGroupsSelectTheSameFiles:
    def test_split_groups_select_the_same_files(self) -> None:
        """Groups differ in `--group` only, so no file is in one group's pool and not another's."""
        names = run_pytest_partition.split_names()
        full_args = run_pytest_partition._PARTITION_FULL_ARGS
        files = tracked_tests()
        for rel in files:
            verdicts = {selects(full_args[name], rel) for name in names}
            assert len(verdicts) == 1, rel
