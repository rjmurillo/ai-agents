"""Collect the pool once and derive every split group from it (issues #6239, #6892).

Not named `test_*.py`, so pytest never collects it. Real legs each get the same
restored map, but a test that collected each group with that leg's own
``--durations-path`` read different files in CI, where only the current leg's
copy exists: group 1 split by timings and groups 2 to 4 split evenly, so the
union missed and doubled tests (PR #6261). Here every group reads one fixture
map, so the result does not depend on whether a cache was restored.

Every split leg collects the whole pool and the plugin keeps its own modules,
so the groups are a pure function of the pool's node IDs and the map. One
``pytest --collect-only`` of the pool plus ``split_by_module`` gives all five
groups. The earlier version ran six full collections, one per group. On
split-4 it took 296.6s and 296.0s of its 300s cap (runs 40047600150 and
40048422175, 2026-10-24) and timed out once on PR #6891 (issue #6892).
``test_pytest_split_hostile_durations.py`` still runs the real plugin flags in
a child process per group, on a small slice of the tree.
"""

from __future__ import annotations

import json
import zlib
from dataclasses import dataclass
from pathlib import Path

from scripts.ci import pytest_module_split as module_split
from scripts.ci import run_pytest_partition as runner
from tests.ci.pytest_split_collect_helpers import collect, pool_args


def _write_fixture_durations(pool: list[str], path: Path) -> None:
    """Deterministic timings for two thirds of the pool; the rest take the unknown path."""
    durations = {
        node_id: (zlib.crc32(node_id.encode()) % 900) / 10 + 0.1
        for index, node_id in enumerate(pool)
        if index % 3
    }
    path.write_text(json.dumps(durations), encoding="utf-8")


@dataclass(frozen=True)
class _CollectedItem:
    """The one attribute ``split_by_module`` reads from a collected item."""

    nodeid: str


def collect_groups(durations_path: Path) -> dict[str, list[str]]:
    """The pool's node IDs, and each split group's, all split by one fixture map."""
    pool = collect(pool_args())
    _write_fixture_durations(pool, durations_path)
    legs = module_split.split_by_module(
        runner.SPLIT_COUNT,
        [_CollectedItem(node_id) for node_id in pool],
        module_split.load_durations(durations_path),
    )
    groups = {
        name: [item.nodeid for item in leg.selected]
        for name, leg in zip(runner.split_names(), legs, strict=True)
    }
    return {"pool": pool, **groups}
