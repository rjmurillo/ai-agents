"""Shared collection helpers for the pytest-split tests (issue #6239).

Imported by test_pytest_split_*.py. The name does not match `test_*.py`, so
pytest never walks it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zlib
from pathlib import Path

from scripts.ci import run_pytest_partition as runner

REPO = Path(__file__).resolve().parents[2]

_COLLECT_TIMEOUT_SECONDS = 280


def collect(args: list[str]) -> list[str]:
    """Node IDs pytest collects for ``args``, in collection order."""
    node_ids, returncode, output = collect_with_code(args)
    assert returncode == 0, output
    return node_ids


def collect_with_code(args: list[str]) -> tuple[list[str], int, str]:
    """Node IDs, pytest's exit code, and the output tail for ``args``."""
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-o",
        "addopts=--import-mode=importlib",
        "--collect-only",
        "-q",
        *args,
    ]
    result = subprocess.run(
        command,
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=_COLLECT_TIMEOUT_SECONDS,
    )
    node_ids = [line for line in result.stdout.splitlines() if "::" in line]
    return node_ids, result.returncode, result.stdout[-2000:] + result.stderr[-2000:]


_STORE_FLAGS = frozenset({"--store-durations", "--clean-durations"})


def without_parallel_flags(args: list[str]) -> list[str]:
    """Drop xdist flags: collection needs no workers.

    Also drops the store flags, which would make a collect-only run rewrite the
    leg's durations file at session finish.
    """
    assert args[:4] == runner._PARALLEL
    return [arg for arg in args[4:] if arg not in _STORE_FLAGS]


def pool_args() -> list[str]:
    """The pool with no split flags: what the four groups must add up to."""
    return [*runner._POOL_IGNORES, "tests/"]


def with_durations_path(args: list[str], path: str) -> list[str]:
    """Point ``--durations-path`` at ``path``, whatever it named before.

    Each leg's own args name its own file (``artifacts/durations-split-N.json``),
    and in CI only the current leg's copy exists. Groups that read different
    maps split the pool differently, so a union taken across them is not the
    pool. Collecting every group against one map is what real legs do.
    """
    index = args.index("--durations-path")
    return [*args[: index + 1], path, *args[index + 2 :]]


def write_fixture_durations(pool: list[str], path: Path) -> None:
    """Write a deterministic durations map for two thirds of the pool.

    The other third has no entry, so a split exercises both the known-timing and
    the unknown-timing paths, and the result never depends on a restored cache.
    """
    durations = {
        node_id: (zlib.crc32(node_id.encode()) % 900) / 10 + 0.1
        for index, node_id in enumerate(pool)
        if index % 3
    }
    path.write_text(json.dumps(durations), encoding="utf-8")
