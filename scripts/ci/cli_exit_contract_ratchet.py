#!/usr/bin/env python3
"""CLI exit-contract ratchet for extracted CI scripts (issue #4068).

ADR-006 extraction moves a workflow ``run:`` block into a Python module. A
``run:`` block executes under ``set -e``, so any command exiting nonzero fails
the step. The natural Python translation returns a sentinel instead: an empty
string, ``None``, an empty list, a warning followed by ``return 0``. When no
caller turns that sentinel into a nonzero exit, the step goes green on a
failure that used to be red. Extraction is a silent-pass generator, not only a
silent-pass detector.

Six instances were found in two in-flight extraction PRs, and three of them
shipped tests asserting the swallow. Every one of those tests asserted on a
helper's return value and never on ``main(argv)``. A helper-level assertion
structurally cannot catch an exit-code defect: the helper correctly reports
failure, and nothing checks that the process does.

So gate the observable property rather than the data flow. A sentinel-tracing
AST scan is high false-positive and only catches shapes already enumerated.
"an extracted CI script whose CLI is never proven to exit nonzero" is
mechanically decidable and catches every one of those shapes at once.

Crediting is deliberately narrow, because a gate that credits the defect shape
is worse than no gate. A nonzero assertion counts only when it shares a test
function with an invocation of that script's ``main`` or with a subprocess call
naming that script's path. Anything looser re-admits the hole: an earlier
revision of this file credited any nonzero assertion anywhere in a file that
named one module, which blessed three helper-only test files, and credited a
bare ``"scripts/ci/<stem>.py"`` string in a workflow-wiring assertion, which is
the first test an extraction PR writes.

The ratchet policy (equality, ``--update`` records a decrease, ``--base-ref``
blocks a PR that widens the allowance) is shared with ``ruff_count_ratchet.py``
and ``taste_count_ratchet.py`` through ``count_ratchet.run``. Only the counting
below is new.

Exit codes (AGENTS.md contract):
    0 - ok (count == baseline, or --update records a decrease)
    1 - regression (count != baseline, or baseline raised vs --base-ref)
    2 - config error (baseline missing or malformed, bad args)
    3 - external error (git could not run)
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.cli_exit_contract_coverage import covered_stems, defines_main
from scripts.ci.count_ratchet import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    EXIT_REGRESSION,
    build_parser,
    run,
    tracked_files,
)

__all__ = [
    "EXIT_CONFIG",
    "EXIT_EXTERNAL",
    "EXIT_OK",
    "EXIT_REGRESSION",
    "MERGE_TREE_BACKED",
    "covered_stems",
    "current_count",
    "defines_main",
    "main",
    "uncovered_scripts",
]

_BASELINE_PATH = Path(__file__).with_name("cli_exit_contract_baseline.txt")

MERGE_TREE_BACKED = True
"""This baseline is registered in ``merge_tree_ratchet_registry.py::RATCHETS``.

Registration is what lets ``count_ratchet.run`` pass a branch that merely holds
a number ``main`` lowered underneath it: the merged result is measured by
``scripts/ci/merge_tree_ratchet_check.py`` instead. Pinned against the registry
by ``tests/ci/test_merge_tree_backing_declarations.py``.
"""

# Both directories hold ADR-006 extraction output and both are invoked straight
# from workflow ``run:`` blocks, so both carry the same exit contract.
_SCRIPT_GLOBS = ("scripts/ci/*.py", ".github/scripts/*.py")
_TEST_GLOBS = ("tests/**/*.py", "tests/*.py")


def _read(repo_root: Path, relative: str) -> str | None:
    try:
        return (repo_root / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def uncovered_scripts(repo_root: Path) -> list[str] | None:
    """Script paths that define ``main`` with no test proving a nonzero exit."""
    scripts = tracked_files(repo_root, _SCRIPT_GLOBS)
    if scripts is None:
        return None
    tests = tracked_files(repo_root, _TEST_GLOBS)
    if tests is None:
        return None

    stems = frozenset(Path(script).stem for script in scripts)
    covered: set[str] = set()
    for path in tests:
        source = _read(repo_root, path)
        if source is not None:
            covered |= covered_stems(source, stems)

    uncovered: list[str] = []
    for script in scripts:
        source = _read(repo_root, script)
        if source is None or not defines_main(source):
            continue
        if Path(script).stem not in covered:
            uncovered.append(script)
    return sorted(uncovered)


def current_count(repo_root: Path) -> int | None:
    """Count of uncovered scripts, or None when the tracked-file scan failed.

    Returning None rather than 0 on failure is load-bearing: a zero from a
    broken scan looks like a clean tree, and ``--update`` would write it into
    the baseline and permanently disarm the gate.
    """
    uncovered = uncovered_scripts(repo_root)
    if uncovered is None:
        return None
    for script in uncovered:
        print(f"  {script}: no test asserts a nonzero exit from main()")
    return len(uncovered)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(
        "CLI exit-contract ratchet for extracted CI scripts (issue #4068).",
        _BASELINE_PATH,
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return run(
        args,
        label="cli exit contract ratchet",
        counter=current_count,
        scan_error="could not list tracked files",
        regression_advice=(
            "A script under scripts/ci or .github/scripts that defines main() "
            "must ship a test asserting a nonzero return from main() on a "
            "failure path the shell original failed on. Assert on main(argv) in "
            "the same test that calls it, not on a helper's return value: a "
            "helper-level assertion cannot catch an exit-code defect "
            "(issue #4068)."
        ),
        merge_tree_backed=MERGE_TREE_BACKED,
    )


if __name__ == "__main__":
    sys.exit(main())
