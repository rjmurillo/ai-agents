"""The split groups cover the pool exactly once.

Issue #6239 acceptance criteria covered here:

- AC2: every pytest CI leg runs its full share. The union of the split
  groups' collected node IDs equals the whole pool's, with no duplicate.
- AC2: no group collects a file that belongs to a dedicated leg or a pin step.

Collection runs `pytest --collect-only` in a child process against the real
tree, so a group that drops or doubles a test fails here and not on a CI leg.
"""

from __future__ import annotations

from collections import Counter

import pytest

from scripts.ci import run_pytest_partition as runner
from tests.ci.pytest_split_collect_helpers import collect
from tests.ci.pytest_split_group_collection import collect_groups


def _check_coverage(collected: dict[str, list[str]], subtests: pytest.Subtests) -> None:
    union = [node_id for name in runner.split_names() for node_id in collected[name]]
    with subtests.test("the pool is not empty"):
        assert len(collected["pool"]) > 1000
    with subtests.test("the union of the groups equals the pool"):
        assert set(union) == set(collected["pool"])
    with subtests.test("no node ID is collected twice"):
        duplicates = [node_id for node_id, count in Counter(union).items() if count > 1]
        assert not duplicates, duplicates[:5]
        assert len(union) == len(collected["pool"])
    for name in runner.split_names():
        with subtests.test("every group collects something", group=name):
            assert collected[name], name
    with subtests.test("no module spans two groups (issue #6846)"):
        homes: dict[str, set[str]] = {}
        for name in runner.split_names():
            for node_id in collected[name]:
                homes.setdefault(node_id.split("::", 1)[0], set()).add(name)
        split_modules = sorted(module for module, groups in homes.items() if len(groups) > 1)
        assert not split_modules, split_modules[:5]


def _check_exclusions(collected: dict[str, list[str]], subtests: pytest.Subtests) -> None:
    excluded = runner._SAFE_PUSH_TESTS | runner._PR_AUTOFIX_TESTS | runner._UNPARTITIONED_TESTS
    for name in runner.split_names():
        with subtests.test("no group collects a dedicated or pinned file", group=name):
            files = {node_id.split("::", 1)[0] for node_id in collected[name]}
            assert not files & excluded, (name, sorted(files & excluded))


@pytest.mark.timeout(300)
class TestSplitGroupsCoverThePool:
    def test_the_split_groups_cover_the_pool_exactly_once(
        self, tmp_path_factory: pytest.TempPathFactory, subtests: pytest.Subtests
    ) -> None:
        """One test, so one collection: worksteal ran a shared fixture once per worker.

        Six tests over a module fixture took 138 s against a 63 s baseline on
        PR #6261, because each worker that drew one of them collected again.
        Subtests keep each check reported on its own.
        """
        collected = collect_groups(tmp_path_factory.mktemp("split") / "durations.json")
        _check_coverage(collected, subtests)
        _check_exclusions(collected, subtests)

    def test_the_dedicated_legs_still_collect_their_files(self) -> None:
        safe_push = collect(runner._PARTITION_FULL_ARGS["safe-push"])
        pr_autofix = collect(runner._PARTITION_FULL_ARGS["pr-autofix"])
        assert {i.split("::", 1)[0] for i in safe_push} == runner._SAFE_PUSH_TESTS
        assert {i.split("::", 1)[0] for i in pr_autofix} == runner._PR_AUTOFIX_TESTS
