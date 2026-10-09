"""Shared collection helpers for the pytest-split tests (issue #6239).

Imported by test_pytest_split_*.py. The name does not match `test_*.py`, so
pytest never walks it.
"""

from __future__ import annotations

import os
import subprocess
import sys
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
