#!/usr/bin/env python3
"""Run a CI pytest partition, narrowed to the import-graph-selected subset.

Each partition in `.github/workflows/pytest.yml` calls this with its name. The
partition's full argument list lives here (Python, not YAML) so the full-vs
subset decision stays out of the workflow per ADR-006. The subset is used only
on push and pull_request events when the import graph maps every changed file
with certainty and this partition owns at least one affected test. `merge_group`
events, any fail-safe verdict, and any partition with no affected test run the
full partition unchanged, so coverage combine always receives non-empty data
for every partition and the run is never less safe than today.

Exit codes follow the repository contract: 0 ok, 2 config, 3 external.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:
    from scripts.ci import run_pytest_non_tmp
    from scripts.test_selection import select_tests
except ModuleNotFoundError:  # pragma: no cover - exercised via direct file execution
    sys.path.insert(0, str(_PROJECT_ROOT))
    from scripts.ci import run_pytest_non_tmp
    from scripts.test_selection import select_tests

_PARALLEL = ["-n", "auto", "--dist", "loadfile"]

# Full argument lists per partition, mirrored from the pytest.yml matrix. These
# are the single source of truth now that the matrix no longer carries
# pytest_args; test_run_pytest_selected.py locks them against drift.
_PARTITION_FULL_ARGS: dict[str, list[str]] = {
    "bulk": [
        *_PARALLEL,
        "--ignore-glob=tests/*/*",
        "--ignore=tests/test_ai_review.py",
        "--ignore=tests/test_verdict.py",
        "--ignore=tests/test_quality_gate.py",
        "--ignore=tests/test_safe_push_pr_branch.py",
        "--ignore=tests/test_mutation_workspace_signals.py",
        "--ignore=tests/test_pr_autofix_late_live_state_gate.py",
        "tests/",
    ],
    "bulk-nested": [
        *_PARALLEL,
        "--ignore=tests/skills/github/test_wait_for_unresolved_zero.py",
        "--ignore=tests/skills/session-end/test_rework_warning.py",
        "tests/build_scripts",
        "tests/ci",
        "tests/claude",
        "tests/claude_mem",
        "tests/commands",
        "tests/context-optimizer",
        "tests/e2e",
        "tests/eval",
        "tests/evals",
        "tests/eval_scenarios",
        "tests/external_signals",
        "tests/fixtures",
        "tests/forgetful",
        "tests/hooks",
        "tests/integration",
        "tests/lib",
        "tests/llm_classification",
        "tests/maintenance",
        "tests/metrics",
        "tests/quality_gate",
        "tests/skillbook",
        "tests/skills",
        "tests/test_memory_sync",
        "tests/test_selection",
        "tests/validation",
        "tests/validation_pre_pr",
        "tests/workflows",
    ],
    "mutation": [*_PARALLEL, "tests/mutation"],
    "safe-push": [
        "tests/test_safe_push_pr_branch.py",
        "tests/test_mutation_workspace_signals.py",
    ],
    "pr-autofix": ["tests/test_pr_autofix_late_live_state_gate.py"],
}

_PARALLEL_PARTITIONS = frozenset({"bulk", "bulk-nested", "mutation"})

# Test files no partition runs as an ordinary member: bulk and bulk-nested
# ignore them and they are covered by dedicated pin steps. If a change affects
# one of these, no partition subset would run it, so the whole run falls back to
# full to avoid a false negative.
_UNPARTITIONED_TESTS = frozenset(
    {
        "tests/test_ai_review.py",
        "tests/test_verdict.py",
        "tests/test_quality_gate.py",
        "tests/skills/github/test_wait_for_unresolved_zero.py",
        "tests/skills/session-end/test_rework_warning.py",
    }
)

_SAFE_PUSH_TESTS = frozenset(
    {"tests/test_safe_push_pr_branch.py", "tests/test_mutation_workspace_signals.py"}
)
_PR_AUTOFIX_TESTS = frozenset({"tests/test_pr_autofix_late_live_state_gate.py"})
_MUTATION_PREFIX = "tests/mutation/"


def classify_partition(rel: str) -> str | None:
    """Which CI partition runs ``rel`` as a member, or None if none does."""
    if rel in _UNPARTITIONED_TESTS:
        return None
    if rel in _SAFE_PUSH_TESTS:
        return "safe-push"
    if rel in _PR_AUTOFIX_TESTS:
        return "pr-autofix"
    if rel.startswith(_MUTATION_PREFIX):
        return "mutation"
    segments = rel.split("/")
    if len(segments) == 2:
        return "bulk"
    return "bulk-nested"


def _partition_subset(partition: str, tests: tuple[str, ...]) -> list[str] | None:
    """Files this partition should run for the selected subset.

    Returns None to signal a full run: an unclassifiable test (false-negative
    guard) or no affected test in this partition (keep coverage non-empty).
    """
    buckets = {test: classify_partition(test) for test in tests}
    if any(owner is None for owner in buckets.values()):
        return None
    mine = [test for test, owner in buckets.items() if owner == partition]
    return mine or None


def resolve_partition_args(
    partition: str,
    event_name: str,
    base_ref: str,
    repo_root: Path,
) -> tuple[list[str], str]:
    """Return the pytest args for ``partition`` and a one-line reason.

    The full partition args are used unless a certain, non-empty subset applies.
    """
    full = _PARTITION_FULL_ARGS[partition]
    if event_name == "merge_group":
        return full, "full: merge_group runs the whole suite"
    changed = select_tests.changed_from_git(repo_root, base_ref)
    if changed is None:
        return full, f"full: could not diff against {base_ref}"
    selection = select_tests.select(changed, repo_root)
    if selection.full:
        return full, f"full: {selection.reason}"
    mine = _partition_subset(partition, selection.tests)
    if mine is None:
        return full, "full: no affected test owned by this partition (or unpartitioned test)"
    flags = _PARALLEL if partition in _PARALLEL_PARTITIONS else []
    return [*flags, *mine], f"subset: {len(mine)} affected test file(s)"


def _emit_summary(partition: str, mode: str, reason: str) -> None:
    print(f"partition={partition} mode={mode} reason={reason}", file=sys.stderr)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"mode={mode}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partition", required=True, choices=sorted(_PARTITION_FULL_ARGS))
    known, passthrough = parser.parse_known_args(argv)

    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    base_ref = os.environ.get("PYTEST_SELECT_BASE", "").strip() or "origin/main"

    args, reason = resolve_partition_args(known.partition, event_name, base_ref, _PROJECT_ROOT)
    mode = "subset" if reason.startswith("subset") else "full"
    _emit_summary(known.partition, mode, reason)

    return run_pytest_non_tmp.main([*passthrough, *args])


if __name__ == "__main__":
    raise SystemExit(main())
