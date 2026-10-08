"""The split groups cover the pool exactly once.

Issue #6239 acceptance criteria covered here:

- AC2: every pytest CI leg runs its full share. The union of the four split
  groups' collected node IDs equals the whole pool's, with no duplicate.
- AC2: no group collects a file that belongs to a dedicated leg or a pin step.

Collection runs `pytest --collect-only` in a child process against the real
tree, so a group that drops or doubles a test fails here and not on a CI leg.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import pytest

from scripts.ci import run_pytest_partition as runner
from tests.ci.pytest_split_collect_helpers import collect, pool_args, without_parallel_flags


@pytest.fixture(scope="module")
def collected() -> dict[str, list[str]]:
    """Collect the pool and each split group once, concurrently."""
    jobs = {"pool": pool_args()}
    for name in runner.split_names():
        jobs[name] = without_parallel_flags(runner._PARTITION_FULL_ARGS[name])
    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = {name: executor.submit(collect, args) for name, args in jobs.items()}
        return {name: future.result() for name, future in futures.items()}


@pytest.mark.timeout(300)
class TestSplitGroupsCoverThePool:
    def test_the_pool_is_not_empty(self, collected: dict[str, list[str]]) -> None:
        assert len(collected["pool"]) > 1000

    def test_the_union_of_the_groups_equals_the_pool(self, collected: dict[str, list[str]]) -> None:
        union = [node_id for name in runner.split_names() for node_id in collected[name]]
        assert set(union) == set(collected["pool"])

    def test_no_node_id_is_collected_twice(self, collected: dict[str, list[str]]) -> None:
        union = [node_id for name in runner.split_names() for node_id in collected[name]]
        duplicates = [node_id for node_id, count in Counter(union).items() if count > 1]
        assert not duplicates, duplicates[:5]
        assert len(union) == len(collected["pool"])

    def test_every_group_collects_something(self, collected: dict[str, list[str]]) -> None:
        for name in runner.split_names():
            assert collected[name], name

    def test_no_group_collects_a_dedicated_or_pinned_file(
        self, collected: dict[str, list[str]]
    ) -> None:
        excluded = runner._SAFE_PUSH_TESTS | runner._PR_AUTOFIX_TESTS | runner._UNPARTITIONED_TESTS
        for name in runner.split_names():
            files = {node_id.split("::", 1)[0] for node_id in collected[name]}
            assert not files & excluded, (name, sorted(files & excluded))

    def test_the_dedicated_legs_still_collect_their_files(self) -> None:
        safe_push = collect(runner._PARTITION_FULL_ARGS["safe-push"])
        pr_autofix = collect(runner._PARTITION_FULL_ARGS["pr-autofix"])
        assert {i.split("::", 1)[0] for i in safe_push} == runner._SAFE_PUSH_TESTS
        assert {i.split("::", 1)[0] for i in pr_autofix} == runner._PR_AUTOFIX_TESTS
