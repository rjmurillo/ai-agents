"""Collect-only stand-in for a pre-push pytest run that cannot finish in its budget.

Issue #6200. Pre-push runs the tests pytest-testmon selects. With no testmon
database the selection is the whole suite: 462 s measured on a 48-thread host,
past the 180 s budget and the 300 s pre-push target (ADR-104). Starting
that run cannot succeed, so the hook collects the suite instead. Collection
imports every test module, so a broken import still blocks the push, and CI
runs every test.

This module holds the pure parts: building the collect-only command, reading
the count out of pytest's summary, and wording the notice. The subprocess
boundary stays in `git_hook_policy.run_pytest`.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence

# pytest -qq ends a collect-only run with one of:
#   "100 tests collected in 0.08s"
#   "49595/49647 tests collected (52 deselected) in 43.55s"
#   "no tests collected (20 deselected) in 0.06s"
_COUNT_RE = re.compile(r"^\W*(\d+)(?:/\d+)? tests? collected\b", re.MULTILINE)
_NONE_RE = re.compile(r"^\W*no tests collected\b", re.MULTILINE)


def collect_only_command(command: Sequence[str], testmon_flags: Collection[str]) -> list[str]:
    """Return ``command`` rewritten to collect without running or touching testmon.

    The testmon flags are dropped so collection never creates or reads
    ``.testmondata``: a half-built database would pass for a finished one.
    ``-n 0`` keeps xdist from starting workers that only collect.
    """
    kept = [token for token in command if token not in testmon_flags]
    return [*kept, "--collect-only", "-qq", "-n", "0"]


def collected_count(output: str) -> int | None:
    """Return the number of tests a collect-only run reported, or None if unreadable."""
    if _NONE_RE.search(output):
        return 0
    matches = _COUNT_RE.findall(output)
    return int(matches[-1]) if matches else None


def total_collected(counts: Sequence[int | None]) -> int | None:
    """Sum the partitions' counts; None when any partition's count is unreadable."""
    if any(count is None for count in counts):
        return None
    return sum(count for count in counts if count is not None)


def deferral_notice(total: int | None, budget_seconds: float, full_suite_env: str) -> str:
    """Say what was not run, why, and who runs it.

    Names the whole suite as the deferred set. Without a database the selection
    is every test, so the size is the collected total, not a guess.
    """
    size = "the whole suite (count unreadable)" if total is None else f"all {total:,} tests"
    return (
        "pytest: no testmon database and no seed, so the selection is the whole "
        "suite.\n"
        f"  Not run locally: {size}. A cold run does not fit the "
        f"{budget_seconds:g}s budget.\n"
        "  Collection passed: every test module imports.\n"
        "  CI runs every test once a pull request exists, and in the merge queue: "
        ".github/workflows/pytest.yml runs every pytest leg in full.\n"
        f"  Set {full_suite_env}=1 to run the whole suite here (ADR-104)."
    )
