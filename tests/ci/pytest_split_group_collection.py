"""Collect the pool and every split group against one durations map (issue #6239).

Not named `test_*.py`, so pytest never collects it. Real legs each get the same
restored map, but a test that collected each group with that leg's own
``--durations-path`` read different files in CI, where only the current leg's
copy exists: group 1 split by timings and groups 2 to 4 split evenly, so the
union missed and doubled tests (PR #6261). Here every group reads one fixture
map, so the result does not depend on whether a cache was restored.
"""

from __future__ import annotations

import json
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts.ci import run_pytest_partition as runner
from tests.ci.pytest_split_collect_helpers import collect, pool_args, without_parallel_flags


def _write_fixture_durations(pool: list[str], path: Path) -> None:
    """Deterministic timings for two thirds of the pool; the rest take the unknown path."""
    durations = {
        node_id: (zlib.crc32(node_id.encode()) % 900) / 10 + 0.1
        for index, node_id in enumerate(pool)
        if index % 3
    }
    path.write_text(json.dumps(durations), encoding="utf-8")


def _with_durations_path(args: list[str], path: str) -> list[str]:
    index = args.index("--durations-path")
    return [*args[: index + 1], path, *args[index + 2 :]]


def collect_groups(durations_path: Path) -> dict[str, list[str]]:
    """The pool's node IDs, and each split group's, all split by one fixture map."""
    pool = collect(pool_args())
    _write_fixture_durations(pool, durations_path)
    jobs = {
        name: _with_durations_path(
            without_parallel_flags(runner._PARTITION_FULL_ARGS[name]), str(durations_path)
        )
        for name in runner.split_names()
    }
    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = {name: executor.submit(collect, args) for name, args in jobs.items()}
        return {"pool": pool, **{name: future.result() for name, future in futures.items()}}
