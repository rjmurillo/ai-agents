"""Compute one expensive value once per xdist run and share it across workers.

Not named `test_*.py`, so pytest never collects it. Used by
test_validation_scripts_are_reachable.py, whose reference graph parses about
1300 sources: 6 s plain and 18 s or more under a coverage tracer, repeated in
every worker at once (issue #6239).

The first worker takes an exclusive lock file and writes the result; the others
poll for it. A worker that waits past the deadline (for example behind a
crashed writer's stale lock) computes locally, so the share can only slow a
worker by the deadline and cannot change the answer. Outside xdist there is no
run id, so the value is computed in place.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

WAIT_SECONDS = 100.0
_POLL_SECONDS = 0.25


def compute_once(label: str, compute: Callable[[], frozenset[str]]) -> frozenset[str]:
    run_uid = os.environ.get("PYTEST_XDIST_TESTRUNUID")
    if not run_uid:
        return compute()
    cache = Path(tempfile.gettempdir()) / f"{label}-{run_uid}.json"
    return _shared(cache, compute)


def _shared(cache: Path, compute: Callable[[], frozenset[str]]) -> frozenset[str]:
    lock = cache.with_suffix(".lock")
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        if cache.exists():
            return frozenset(json.loads(cache.read_text(encoding="utf-8")))
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            time.sleep(_POLL_SECONDS)
            continue
        os.close(handle)
        try:
            return _write_result(cache, compute)
        finally:
            lock.unlink(missing_ok=True)
    return compute()


def _write_result(cache: Path, compute: Callable[[], frozenset[str]]) -> frozenset[str]:
    result = compute()
    partial = cache.with_suffix(f".{os.getpid()}.tmp")
    partial.write_text(json.dumps(sorted(result)), encoding="utf-8")
    os.replace(partial, cache)
    return result
