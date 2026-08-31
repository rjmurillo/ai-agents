"""Subprocess encoding convention count ratchet (issue #4261).

Counts calls to subprocess.run / subprocess.Popen / subprocess.check_output /
subprocess.check_call that use text mode (text= or encoding=) but omit errors=.
The count must not exceed the baseline. Improvements are allowed; regressions
block. The baseline may only fall.

Stdlib only: this runs by path in CI and must not depend on the project's
import graph.

Exit codes (AGENTS.md contract):
    0 - ok (count <= baseline)
    1 - regression (count > baseline, or a successful fork-point comparison
        proves the recorded baseline sits above the one at --base-ref)
    2 - config error (baseline missing or malformed, fork baseline absent,
        bad args)
    3 - external error (checker, git, or fork baseline read failed)
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.count_ratchet import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    EXIT_REGRESSION,
    build_parser,
    run,
    tracked_files,
)
from scripts.validation.check_subprocess_encoding import find_all_violations

__all__ = [
    "EXIT_CONFIG",
    "EXIT_EXTERNAL",
    "EXIT_OK",
    "EXIT_REGRESSION",
    "MERGE_TREE_BACKED",
    "current_count",
    "main",
]

_BASELINE_PATH = Path(__file__).with_name("subprocess_encoding_count_baseline.txt")
_FIXTURE_PREFIX = "tests/hooks/fixtures/"

MERGE_TREE_BACKED = False
"""This baseline is NOT registered in ``merge_tree_ratchet_registry.py``.

The other five count ratchets under ``scripts/ci`` are, so their branch-tree
comparison may pass a branch that merely holds a number ``main`` lowered
underneath it: ``scripts/ci/merge_tree_ratchet_check.py`` measures the merged
result for them. This one has no such gate, and it runs only from
``.github/workflows/pytest.yml`` (no lefthook job, no pr-validation step), so
the ``--base-ref`` comparison is its whole stale-branch guard. Waiving it here
would let a branch cut before a lowering carry its old ceiling over the base's
current one: with baseline 238 against a tree of 234, four new violations
measure 238, pass under the stale ceiling, and land above ``main``'s 234.

Registering it would be the other fix and is deliberately not taken here: it
adds a sixth evaluation to the local count-ratchets aggregate and to
pr-validation, which is a gate change (ci-scripts MUST-13) rather than a defect
repair. Pinned against the registry by
``tests/ci/test_merge_tree_backing_declarations.py``, so flipping this to True
without registering the baseline fails.
"""


def current_count(repo_root: Path) -> int | None:
    """Total subprocess encoding violations, or None if the checker failed."""
    py_files = tracked_files(repo_root, ("*.py", "**/*.py"))
    if py_files is None:
        return None

    # Filter out fixture exemptions and non-existent files
    py_files = [
        f for f in py_files
        if not f.startswith(_FIXTURE_PREFIX) and (repo_root / f).is_file()
    ]
    if not py_files:
        return 0

    try:
        return len(find_all_violations(repo_root, [repo_root / f for f in py_files]))
    except OSError as error:
        sys.stderr.write(f"Checker failed: {error}\n")
        return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(
        "Subprocess encoding convention count ratchet (issue #4261).",
        _BASELINE_PATH,
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return run(
        args,
        label="subprocess encoding count ratchet",
        counter=current_count,
        scan_error="check_subprocess_encoding.py failed to run",
        regression_advice=(
            "New subprocess calls that use text= or encoding= must also pass "
            "errors= (issue #4261). Add errors=\"replace\" to the call, or "
            "errors=\"strict\" if a decode failure is an error condition."
        ),
        merge_tree_backed=MERGE_TREE_BACKED,
    )


if __name__ == "__main__":
    raise SystemExit(main())
