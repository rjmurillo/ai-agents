"""Run an ordered batch scan in worker processes with a serial fallback.

The result and the first exception match the serial run: batches are contiguous
and results are read in submission order. A pool that cannot start or dies falls
back to calling ``scan`` on the whole input in this process.
"""

from __future__ import annotations

import multiprocessing
import os
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from typing import TypeVar

# Parsing thousands of files is CPU bound, so a large input fans out to processes. A small
# input stays in-process: a pool costs more than it saves, so small test fixtures run
# serially unless a test calls scan_in_processes directly or lowers MIN_BYTES.
MIN_BYTES = 4_000_000
MAX_WORKERS = 8
BATCHES_PER_WORKER = 4

Item = tuple[str, str]
T = TypeVar("T")


def split_batches(items: list[Item], count: int) -> list[list[Item]]:
    """Split ``items`` into at most ``count`` contiguous batches of similar byte size."""
    target = max(1, sum(len(text) for _, text in items) // count)
    batches: list[list[Item]] = [[]]
    size = 0
    for item in items:
        if size >= target and len(batches) < count:
            batches.append([])
            size = 0
        batches[-1].append(item)
        size += len(item[1])
    return batches


def worker_count(items: list[Item]) -> int:
    """Workers worth starting for ``items``; 1 means scan in this process."""
    if sum(len(text) for _, text in items) < MIN_BYTES:
        return 1
    return min(os.process_cpu_count() or 1, MAX_WORKERS)


def scan_in_processes(
    scan: Callable[[list[Item]], list[T]], items: list[Item], workers: int
) -> list[T]:
    """Return ``scan(items)``, computed over batches in ``workers`` processes (1: in this one).

    ``scan`` must be a module-level function so worker processes can import it.
    """
    if workers <= 1:
        return scan(items)
    batches = split_batches(items, workers * BATCHES_PER_WORKER)
    try:
        # forkserver, not fork: the caller may hold threads, and fork would copy their locks.
        context = multiprocessing.get_context("forkserver")
    except ValueError:
        return scan(items)
    try:
        with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
            futures = [pool.submit(scan, batch) for batch in batches]
            try:
                return [found for future in futures for found in future.result()]
            finally:
                for future in futures:
                    future.cancel()
    except (BrokenProcessPool, OSError):
        return scan(items)
