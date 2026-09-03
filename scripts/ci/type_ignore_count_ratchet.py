#!/usr/bin/env python3
"""Whole-repo ``# type: ignore`` comment-count ratchet.

Counts ``# type: ignore`` comments in tracked Python files and enforces a
non-growing ceiling. The security-suppression gate in
``scripts/validation/git_hook_policy.py`` explicitly excludes type-ignore
comments (see the comment above SECURITY_SUPPRESSION_RE in that file).
This ratchet fills that gap: the total count across the whole repo can
never grow, so a contributor cannot accumulate suppressions across many
commits that each stay under the changed-line radar.

Keeping type-ignore suppressions separate from the security-suppression
machinery reflects the architectural intent in issue #4039: type-quality
concerns belong in the type-quality gate, not bundled with security
enforcement.

Scope is git-TRACKED Python files. The scan itself is a simple grep over file
contents; no mypy invocation is needed.

Stdlib only: this runs by path in CI and must not depend on the project's
import graph.

Exit codes (AGENTS.md contract):
    0 - ok (count <= baseline)
    1 - regression (count > baseline, or baseline raised vs --base-ref)
    2 - config error (baseline missing or malformed, bad args)
    3 - external error (could not read files)
"""

from __future__ import annotations

import re
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

__all__ = [
    "EXIT_CONFIG",
    "EXIT_EXTERNAL",
    "EXIT_OK",
    "EXIT_REGRESSION",
    "MERGE_TREE_BACKED",
    "_SELF_REFERENTIAL_FILES",
    "current_count",
    "main",
]

_BASELINE_PATH = Path(__file__).with_name("type_ignore_count_baseline.txt")

MERGE_TREE_BACKED = True
"""This baseline is registered in ``merge_tree_ratchet_registry.py::RATCHETS``.

Registration is what lets ``count_ratchet.run`` pass a branch that merely holds
a number ``main`` lowered underneath it: the merged result is measured by
``scripts/ci/merge_tree_ratchet_check.py`` instead. Pinned against the registry
by ``tests/ci/test_merge_tree_backing_declarations.py``.
"""

# Match ``# type: ignore`` with optional bracket qualifier, allowing whitespace
# variations. Only Python (.py) files are counted; other extensions do not use
# mypy-style type ignores.
_TYPE_IGNORE_RE = re.compile(r"#\s*type:\s*ignore(?:\[[^\]]*\])?")

_PY_GLOBS = ("*.py",)

# Files that describe or test the ``# type: ignore`` syntax without using it as
# a real mypy suppression. Counting them would inflate the baseline by the
# number of string literals and docstring examples they contain, making the
# ratchet 20% noise about itself (issue #4039).
#
# Paths are relative to the repo root (the result of ``tracked_files``).
_SELF_REFERENTIAL_FILES: frozenset[str] = frozenset(
    [
        "scripts/ci/type_ignore_count_ratchet.py",
        "tests/ci/test_type_ignore_count_ratchet.py",
    ]
)


def current_count(repo_root: Path) -> int | None:
    """Count ``# type: ignore`` comments in tracked Python files.

    Returns the total count, or None if a file could not be read. Returning
    None rather than 0 on any I/O failure is load-bearing: a zero from a
    crashed read would look like a clean tree and ``--update`` would write that
    zero into the baseline, permanently disarming the gate.

    Files in ``_SELF_REFERENTIAL_FILES`` are excluded: they describe or test
    the ``# type: ignore`` syntax in string literals and docstrings without
    using it as a real suppression, and counting them inflates the baseline
    with noise about the gate itself (issue #4039).
    """
    files = tracked_files(repo_root, _PY_GLOBS)
    if files is None:
        return None
    if not files:
        return 0

    total = 0
    for path_str in files:
        if path_str in _SELF_REFERENTIAL_FILES:
            continue
        path = repo_root / path_str
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            sys.stderr.write(f"could not read {path}: {exc}\n")
            return None
        total += len(_TYPE_IGNORE_RE.findall(text))
    return total


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(
        "Whole-repo type-ignore comment-count ratchet (issue #4039).",
        _BASELINE_PATH,
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return run(
        args,
        label="type-ignore count ratchet",
        counter=current_count,
        scan_error="could not read tracked Python files",
        regression_advice=(
            "New '# type" ": ignore' comments cannot merge. Fix the type error, "
            "or if suppression is genuinely required, coordinate a baseline "
            "update with a reasoned explanation (issue #4039)."
        ),
        merge_tree_backed=MERGE_TREE_BACKED,
    )


if __name__ == "__main__":
    sys.exit(main())
