"""Real pytest collection for relocation checks in ``validation_record.py``.

``relocation_evidence`` holds the pure shape checks. This module checks the
claimed ids against what pytest really collects (issue #6506,
review-gates-03). ``collect_tests`` is the one place that starts a
subprocess: a fixed ``pytest --collect-only`` run. The record's own
``collect_command`` is never executed. ``collected_defects`` takes the
collector as an argument, so tests can pass a fake one.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from relocation_evidence import name_diff, path_key, test_names

_COLLECT_TIMEOUT_SECONDS = 300

# A collector takes the moved_to module paths and returns the collected test
# ids, or raises CollectionError when collection cannot be trusted.
Collector = Callable[[Sequence[str]], list[str]]


class CollectionError(RuntimeError):
    """Real test collection failed, so the relocation claim cannot be verified."""


class PytestUnavailableError(RuntimeError):
    """pytest is not importable here, a config error rather than a record defect.

    Deliberately not a ``CollectionError``: that one becomes a record defect
    (exit 1), while a missing tool means the check never ran (exit 2).
    """


def collect_tests(paths: Sequence[str], repo_root: Path) -> list[str]:
    """Collect test ids from ``paths`` with a fixed pytest command in ``repo_root``.

    The validator never runs the record's own ``collect_command``: that string
    is agent-supplied, and executing it would let the record run arbitrary
    commands. The argv here is fixed, so only the module paths vary, and they
    are checked to sit under ``tests/`` with no ``..`` by the caller before this
    runs; ``validation_record`` skips collection when that scope check fails.

    Trust model: pytest imports each named module, every ``conftest.py`` from
    its rootdir down to that module (the repository root one included), and
    every installed pytest plugin. The scope check limits which test modules
    load, not what code runs, so run this only on a checkout you trust.
    """
    if importlib.util.find_spec("pytest") is None:
        raise PytestUnavailableError(
            f"pytest is not installed for {sys.executable}; install it to verify relocations"
        )
    # --override-ini=addopts= drops the repo's addopts: its -v cancels -q and
    # prints a tree with no "::" ids, which would collect zero tests.
    # -p no:warnings drops the warnings summary: a warning text holding "::"
    # would otherwise be read as a test id.
    argv = [
        sys.executable,
        "-m",
        "pytest",
        "--override-ini=addopts=",
        "--import-mode=importlib",
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
        "-p",
        "no:warnings",
    ]
    # PYTEST_ADDOPTS reaches pytest too: an inherited -v would cancel -q.
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
    try:
        result = subprocess.run(
            [*argv, "--", *paths],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=_COLLECT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CollectionError(f"pytest collection could not run: {exc}") from exc
    if result.returncode != 0:
        raise CollectionError(
            f"pytest collection exited {result.returncode}: {_failure_detail(result)}"
        )
    return [line.strip() for line in result.stdout.splitlines() if "::" in line]


_DETAIL_LINES = 3


def _failure_detail(result: subprocess.CompletedProcess[str]) -> str:
    """Name the cause of a failed collection in a few lines.

    pytest's last line is only the tally ("no tests collected, 1 error"). The
    cause sits in the ``ERROR <path>`` summary lines and the first ``E   ``
    traceback line, so keep those, capped, and end with the tally.
    """
    lines = (result.stdout + result.stderr).strip().splitlines()
    if not lines:
        return "no output"
    errors = [line.strip() for line in lines if line.startswith("ERROR ")]
    first_e = next((line.strip() for line in lines if line.startswith("E   ")), None)
    cause = errors[:_DETAIL_LINES] + ([first_e] if first_e else [])
    return " | ".join([*cause, lines[-1].strip()])


def collected_defects(where: str, target: dict[str, Any], collector: Collector) -> list[str]:
    """Compare ``tests_after`` with real collection of the ``moved_to`` modules.

    Call only once ``relocation_defects`` found no defect, so the evidence
    shape is known to be valid. Because ``tests_before`` must equal
    ``tests_after`` by name, the comparison covers both lists.
    """
    evidence = target["relocation_evidence"]
    after, _ = test_names(where, "tests_after", evidence["tests_after"])
    destination = sorted({path_key(item) for item in evidence["moved_to"]})
    try:
        real, shape = test_names(where, "collected", collector(destination))
    except CollectionError as exc:
        return [f"{where}: relocation_evidence could not be verified by real collection: {exc}"]
    if shape:
        return [f"{where}: real collection of the moved_to files found no tests"]
    if real != after:
        return [
            f"{where}: relocation_evidence.tests_after does not match real collection of the "
            f"moved_to files ({sum(after.values())} claimed, {sum(real.values())} collected); "
            f"{name_diff(after, real)}"
        ]
    return []
