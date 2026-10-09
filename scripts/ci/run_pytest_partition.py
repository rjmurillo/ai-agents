#!/usr/bin/env python3
"""Run one CI pytest partition in full.

Each leg in `.github/workflows/pytest.yml` calls this with its partition name
(`split-1` through `split-4`, `safe-push`, `pr-autofix`).
The partition's argument list lives here (Python, not YAML) per ADR-006. Every
leg runs its whole share on every event, so coverage combine always receives
data from every partition.

Exit codes follow the repository contract: 0 ok, 2 config (an unknown or
missing partition), otherwise the pytest runner's own code.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:
    from scripts.ci import run_pytest_non_tmp
except ModuleNotFoundError:  # pragma: no cover - exercised via direct file execution
    sys.path.insert(0, str(_PROJECT_ROOT))
    from scripts.ci import run_pytest_non_tmp

# `loadfile` sends every test in one file to one worker. That is the weakest
# distribution mode xdist offers and the point: module-scoped fixtures, module
# state, and file-local temp directories keep behaving the way they do serially.
# CI partitions and the local pre-push hook (scripts/validation/git_hook_policy.py)
# both read this one value.
PYTEST_DIST_MODE = "loadfile"

_PARALLEL = ["-n", "auto", "--dist", PYTEST_DIST_MODE]

# The pool is every test file outside the dedicated legs and the unpartitioned
# pins, split into SPLIT_COUNT groups by recorded duration (pytest-split).
#
# Nobody maintains a durations file. Timings ride in the Actions cache:
# pytest.yml restores the newest map to DURATIONS_RESTORE_PATH on every split
# leg, and the test-durations job saves a fresh one only on a push to main.
# pytest-split has a single `--durations-path` that it both reads and writes, so
# this runner copies the restored map to a per-leg file (_leg_durations_path)
# and points pytest-split at the copy. The leg then reads the restored timings,
# and `--store-durations --clean-durations` rewrites the copy with only the tests
# that leg ran. The four legs run disjoint groups, so their files union into the
# full map (scripts/testing/duration_split_merge.py) and a deleted test drops out
# of the cache on the next main run. The restored file is never written.
#
# When nothing restored, pytest-split splits evenly by test count and this runner
# emits a CI warning annotation. A test missing from the map gets the average
# recorded duration. Either way every test still runs; only the balance degrades.
#
# Each group must stay under the ten minute job contract of issue #4854.
# split-1 is the `primary` matrix leg and carries the extra pin, lint, and
# ratchet steps in pytest.yml, so its share must leave room for them.
#
# Both paths stay relative on purpose: run_pytest_non_tmp starts pytest with
# cwd=PROJECT_ROOT, so pytest-split resolves them against the repo root whatever
# directory this script is launched from (a test pins that).
SPLIT_COUNT = 4
DURATIONS_RESTORE_PATH = ".pytest-split/durations.json"
LEG_DURATIONS_DIR = "artifacts"
SPLITTING_ALGORITHM = "duration_based_chunks"
_SPLIT_PREFIX = "split-"

_SAFE_PUSH_ARGS = [
    "tests/test_safe_push_pr_branch.py",
    "tests/test_mutation_workspace_signals.py",
]
_PR_AUTOFIX_ARGS = ["tests/test_pr_autofix_late_live_state_gate.py"]
_SAFE_PUSH_TESTS = frozenset(_SAFE_PUSH_ARGS)
_PR_AUTOFIX_TESTS = frozenset(_PR_AUTOFIX_ARGS)

# Test files no split group runs: dedicated pin steps cover the first four.
_UNPARTITIONED_TESTS = frozenset(
    {
        "tests/test_ai_review.py",
        "tests/test_verdict.py",
        "tests/test_quality_gate.py",
        "tests/skills/github/test_wait_for_unresolved_zero.py",
    }
)

_POOL_IGNORES = [
    f"--ignore={path}"
    for path in sorted(_UNPARTITIONED_TESTS | _SAFE_PUSH_TESTS | _PR_AUTOFIX_TESTS)
]


def split_names() -> list[str]:
    """The split group partition names, ``split-1`` through ``split-N``."""
    return [f"{_SPLIT_PREFIX}{index}" for index in range(1, SPLIT_COUNT + 1)]


def _leg_durations_path(partition: str) -> str:
    """Where one split leg stores its timings, uploaded with that leg's artifacts."""
    return f"{LEG_DURATIONS_DIR}/durations-{partition}.json"


def _split_group_args(index: int) -> list[str]:
    return [
        *_PARALLEL,
        "--splits",
        str(SPLIT_COUNT),
        "--group",
        str(index),
        "--splitting-algorithm",
        SPLITTING_ALGORITHM,
        "--store-durations",
        "--clean-durations",
        "--durations-path",
        _leg_durations_path(f"{_SPLIT_PREFIX}{index}"),
        *_POOL_IGNORES,
        "tests/",
    ]


# Full argument lists per partition. These are the single source of truth; the
# pytest.yml matrix carries only the partition name.
_PARTITION_FULL_ARGS: dict[str, list[str]] = {
    **{name: _split_group_args(i) for i, name in enumerate(split_names(), start=1)},
    "safe-push": list(_SAFE_PUSH_ARGS),
    "pr-autofix": list(_PR_AUTOFIX_ARGS),
}

_PARALLEL_PARTITIONS = frozenset(split_names())

_DIGEST_PREFIX_CHARS = 12


def _durations_digest() -> str:
    """First 12 hex chars of the restored map's SHA-256, or ``missing``."""
    path = _PROJECT_ROOT / DURATIONS_RESTORE_PATH
    if not path.is_file():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:_DIGEST_PREFIX_CHARS]


def _seed_leg_durations(partition: str) -> None:
    """Give pytest-split this leg's file: a copy of the restored map, or nothing.

    A stale leg file from an earlier local run is removed when nothing restored,
    so a leg never reads timings the missing-file warning says it lacks.
    """
    leg_file = _PROJECT_ROOT / _leg_durations_path(partition)
    leg_file.parent.mkdir(parents=True, exist_ok=True)
    restored = _PROJECT_ROOT / DURATIONS_RESTORE_PATH
    if restored.is_file():
        shutil.copyfile(restored, leg_file)
    else:
        leg_file.unlink(missing_ok=True)


def _summary_line(partition: str) -> str:
    """The stderr line that says which share and which timings this leg used."""
    line = f"partition={partition} mode=full"
    if partition not in _PARALLEL_PARTITIONS:
        return line
    group = partition.removeprefix(_SPLIT_PREFIX)
    return (
        f"{line} splits={SPLIT_COUNT} group={group} durations={DURATIONS_RESTORE_PATH} "
        f"durations_sha256={_durations_digest()}"
    )


def classify_partition(rel: str) -> str | None:
    """Which CI leg kind runs ``rel``: ``split``, ``safe-push``, ``pr-autofix``, or None.

    The split groups share one pool, so any pool member classifies as ``split``;
    which group runs it depends on the durations file.
    """
    if rel in _UNPARTITIONED_TESTS:
        return None
    if rel in _SAFE_PUSH_TESTS:
        return "safe-push"
    if rel in _PR_AUTOFIX_TESTS:
        return "pr-autofix"
    return "split"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partition", choices=sorted(_PARTITION_FULL_ARGS), required=True)
    known, passthrough = parser.parse_known_args(argv)

    print(_summary_line(known.partition), file=sys.stderr)
    if known.partition in _PARALLEL_PARTITIONS:
        if _durations_digest() == "missing":
            print(
                f"::warning title=pytest-split::{DURATIONS_RESTORE_PATH} did not restore "
                "from the Actions cache; this leg split by test count, so leg times "
                "may be unbalanced."
            )
        _seed_leg_durations(known.partition)
    return run_pytest_non_tmp.main([*passthrough, *_PARTITION_FULL_ARGS[known.partition]])


if __name__ == "__main__":
    raise SystemExit(main())
