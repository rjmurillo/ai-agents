#!/usr/bin/env python3
"""Run one CI pytest partition in full.

Each leg in `.github/workflows/pytest.yml` calls this with its partition name.
The partition's argument list lives here (Python, not YAML) per ADR-006. Every
leg runs its whole share on every event, so coverage combine always receives
data from every partition.

Exit codes follow the repository contract: 0 ok, 2 config (an unknown or
missing partition), otherwise the pytest runner's own code.
"""

from __future__ import annotations

import argparse
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

# The nested test directories, split in two so each CI job stays under the ten
# minute contract of issue #4854. Per-directory test time on a main run
# (bulk-nested artifact, 27679 tests, 1504s summed): validation 645, ci 435,
# skills 113, eval 103, commands 67, build_scripts 66, every other directory
# under 17 each. `ci` holds the heaviest files, so the second partition takes
# ci, skills, eval, commands and build_scripts (about 784s) and the first takes
# validation plus the small directories (about 720s).
_NESTED_CI_DIRS = ("build_scripts", "ci", "commands", "eval", "skills")
_NESTED_REST_DIRS = (
    "claude",
    "claude_mem",
    "context-optimizer",
    "e2e",
    "evals",
    "external_signals",
    "fixtures",
    "hooks",
    "integration",
    "lib",
    "llm_classification",
    "maintenance",
    "metrics",
    "quality_gate",
    "skillbook",
    "test_selection",
    "validation",
    "validation_pre_pr",
    "workflows",
)

# Full argument lists per partition, mirrored from the pytest.yml matrix. These
# are the single source of truth now that the matrix no longer carries
# pytest_args.
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
        *(f"tests/{name}" for name in _NESTED_REST_DIRS),
    ],
    "bulk-nested-ci": [
        *_PARALLEL,
        "--ignore=tests/skills/github/test_wait_for_unresolved_zero.py",
        *(f"tests/{name}" for name in _NESTED_CI_DIRS),
    ],
    "mutation": [*_PARALLEL, "tests/mutation"],
    "safe-push": [
        "tests/test_safe_push_pr_branch.py",
        "tests/test_mutation_workspace_signals.py",
    ],
    "pr-autofix": ["tests/test_pr_autofix_late_live_state_gate.py"],
}

_PARALLEL_PARTITIONS = frozenset({"bulk", "bulk-nested", "bulk-nested-ci", "mutation"})

# Test files no partition runs as an ordinary member: bulk and bulk-nested
# ignore them and they are covered by dedicated pin steps.
_UNPARTITIONED_TESTS = frozenset(
    {
        "tests/test_ai_review.py",
        "tests/test_verdict.py",
        "tests/test_quality_gate.py",
        "tests/skills/github/test_wait_for_unresolved_zero.py",
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
    if segments[1] in _NESTED_CI_DIRS:
        return "bulk-nested-ci"
    return "bulk-nested"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partition", required=True, choices=sorted(_PARTITION_FULL_ARGS))
    known, passthrough = parser.parse_known_args(argv)

    print(f"partition={known.partition} mode=full", file=sys.stderr)
    return run_pytest_non_tmp.main([*passthrough, *_PARTITION_FULL_ARGS[known.partition]])


if __name__ == "__main__":
    raise SystemExit(main())
