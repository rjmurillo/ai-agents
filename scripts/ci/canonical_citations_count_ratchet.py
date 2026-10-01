#!/usr/bin/env python3
"""Uncited mirror-claim count ratchet: fail only when the count grows.

Issue #5636, decision D11. ``scripts/validation/check_canonical_citations.py``
reports a mirror-claim ("matches the", "mirrors ", "aligned with") that cites no
canonical path, but exits 0 unless ``STRICT_CANONICAL_CHECK=1``, and strict mode
is red on the current corpus. This gate freezes the violation count in
``canonical_citations_count_baseline.txt``. The count may fall (lower the
baseline with ``--update``) and may never rise, so the corpus cannot grow new
uncited claims while the existing ones are cleaned up.

The count is the number of violations ``STRICT_CANONICAL_CHECK=1`` reports:
``check_canonical_citations.scan_file`` is called once per file, so the two
agree by construction. One difference is deliberate, per
``.claude/rules/ci-scripts.md`` MUST 9: the checker walks the directory tree
with ``rglob``, which reads untracked files too. This ratchet lists git-TRACKED
Python files under the same four scan roots, so the same commit scores the same
on every machine.

Stdlib only: this runs by path in CI and must not depend on the project's
import graph.

Exit codes (AGENTS.md contract):
    0 - ok (count <= baseline)
    1 - regression (count > baseline, or baseline raised vs --base-ref)
    2 - config error (baseline missing or malformed, bad args)
    3 - external error (git or a file read failed)
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
from scripts.validation.check_canonical_citations import scan_file

__all__ = [
    "EXIT_CONFIG",
    "EXIT_EXTERNAL",
    "EXIT_OK",
    "EXIT_REGRESSION",
    "MERGE_TREE_BACKED",
    "current_count",
    "main",
]

_BASELINE_PATH = Path(__file__).with_name("canonical_citations_count_baseline.txt")

# The four roots ``check_canonical_citations._scan_roots`` inspects.
_SCAN_ROOT_PREFIXES: tuple[str, ...] = (
    ".claude/hooks/",
    "scripts/validation/",
    "build/scripts/",
    ".claude/skills/",
)

# ``scan_file`` returns a Violation with this token when it cannot read a file.
# That is a scan failure, never a violation to count.
_READ_ERROR_TOKEN = "read_error"

MERGE_TREE_BACKED = False
"""This baseline is NOT registered in ``merge_tree_ratchet_registry.py``.

The ``--base-ref`` comparison is therefore the whole stale-branch guard for this
ratchet, the same position ``subprocess_encoding_count_ratchet.py`` holds.
Pinned against the registry by
``tests/ci/test_merge_tree_backing_declarations.py``.
"""


def _in_scan_roots(path_str: str) -> bool:
    """True for a tracked path the citation checker would inspect."""
    parts = path_str.split("/")
    return path_str.startswith(_SCAN_ROOT_PREFIXES) and "__pycache__" not in parts


def current_count(repo_root: Path) -> int | None:
    """Count uncited mirror-claims in tracked files, or None if a scan failed.

    None rather than 0 on any failure is load-bearing: a zero from a crashed
    read looks like a clean tree, and ``--update`` would write that zero into
    the baseline and disarm the gate.
    """
    files = tracked_files(repo_root, ("*.py",))
    if files is None:
        return None
    total = 0
    for path_str in files:
        if not _in_scan_roots(path_str) or not (repo_root / path_str).is_file():
            continue
        violation = scan_file(repo_root / path_str)
        if violation is None:
            continue
        if violation.matched_token == _READ_ERROR_TOKEN:
            sys.stderr.write(f"could not read {path_str}: {violation.excerpt}\n")
            return None
        total += 1
    return total


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(
        "Uncited mirror-claim count ratchet (issue #5636, D11).",
        _BASELINE_PATH,
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return run(
        args,
        label="canonical citations count ratchet",
        counter=current_count,
        scan_error="could not scan tracked Python files for mirror-claims",
        regression_advice=(
            "A docstring or top-of-file comment says 'matches', 'mirrors', or "
            "'aligned with' without citing a canonical path. Add the path and "
            "quote the contract "
            "(.claude/rules/canonical-source-mirror.md). Find it with "
            "STRICT_CANONICAL_CHECK=1 uv run python "
            "scripts/validation/check_canonical_citations.py."
        ),
        merge_tree_backed=MERGE_TREE_BACKED,
    )


if __name__ == "__main__":
    sys.exit(main())
