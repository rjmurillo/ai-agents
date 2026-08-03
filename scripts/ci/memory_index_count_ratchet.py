#!/usr/bin/env python3
"""Whole-repo unindexed-memory count ratchet (issue #4313).

``validate_memory_tier.py`` has always computed a strict count and thrown it
away: ``lefthook.yml`` called it without ``--ci`` and the workflow passed
``--ci`` under ``continue-on-error``. Issue #4313 measured 400 atomic memories
that no domain index references, which means the majority of written memories
are unreachable through the retrieval path ``AGENTS.md`` points at.

Adding ``--ci`` to the hook closes the loop and is unshippable. It promotes
every one of those legacy warnings to an error, so the gate blocks every commit
that touches ``.serena/memories/**``, including the commits that would index the
backlog. Issue #4313 anticipated this and named the remedy: "A ratchet fits the
repo's existing pattern and avoids a 400-file cleanup blocking unrelated work."
This is that ratchet. Every currently-unindexed memory keeps passing on day one,
the count cannot rise, and indexing any of them lowers it.

The scan runs WITHOUT ``--ci`` on purpose. Under ``--ci`` the validator moves
warnings into errors and exits 1, which is indistinguishable from a genuine
structural failure such as a broken index reference. Without it, exit 0 means
the scan completed and its warning list can be trusted, and a non-zero exit
means a real error the ratchet must not paper over: the counter returns None and
``run`` reports an external error instead of a violation count.

Both warning shapes are counted, the unreferenced atomic file and the
unreferenced domain index, because both are what the discarded ``--ci`` exit
code covered. Counting only the larger population would let a new orphaned
domain index through the gate this exists to close.

Scope is git-TRACKED files. ``validate_orphan_atomics`` reaches the tree with
``rglob``, so an untracked scratch memory on one contributor's disk counts as a
violation for them and not for CI, which is the phantom-count failure
``ruff_count_ratchet.py`` was written to avoid. A domain-index warning names an
index file rather than a path under a subdirectory; those live at the top level
of the memories directory and are filtered by the same tracked set.

Stdlib only: this runs by path in CI (``python scripts/ci/<name>.py``) and must
not depend on the project's import graph.

Exit codes (AGENTS.md contract):
    0 - ok (count <= baseline, or --update records a decrease)
    1 - regression (count > baseline, or baseline raised vs --base-ref)
    2 - config error (baseline missing or malformed, bad args)
    3 - external error (the validator could not run)
"""

from __future__ import annotations

import subprocess
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
    "current_count",
    "list_violations",
    "main",
]

_BASELINE_PATH = Path(__file__).with_name("memory_index_count_baseline.txt")

_VALIDATOR = Path("scripts/validate_memory_tier.py")

_MEMORIES_DIR = ".serena/memories"

_WARNING_PREFIX = "WARNING: "


def _warning_lines(repo_root: Path) -> list[str] | None:
    """Every ``WARNING:`` body from a healthy scan, or None when it failed.

    Returning None rather than an empty list on any failure is load-bearing. A
    zero from a crashed validator would look like a fully indexed tree, and
    ``--update`` would write that zero into the baseline and permanently disarm
    the gate.
    """
    validator = repo_root / _VALIDATOR
    if not validator.is_file():
        sys.stderr.write(f"memory tier validator not found at {_VALIDATOR}\n")
        return None
    try:
        proc = subprocess.run(
            [sys.executable, str(_VALIDATOR), "--path", _MEMORIES_DIR],
            cwd=repo_root,
            capture_output=True,
            text=True,
            errors="replace",
            encoding="utf-8",
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        sys.stderr.write(f"memory tier validator could not be launched: {exc}\n")
        return None
    if proc.returncode != 0:
        sys.stderr.write(
            "memory tier validator reported a structural error, which is not a "
            f"warning count (exit {proc.returncode}). Fix the errors it names first.\n"
        )
        sys.stderr.write(proc.stdout[-4000:])
        return None
    return [
        line[len(_WARNING_PREFIX):].strip()
        for line in proc.stdout.splitlines()
        if line.startswith(_WARNING_PREFIX)
    ]


def _tracked_relative_paths(repo_root: Path) -> set[str] | None:
    """Tracked memory files as paths relative to the memories directory."""
    files = tracked_files(repo_root, (f"{_MEMORIES_DIR}/**",))
    if files is None:
        return None
    prefix = f"{_MEMORIES_DIR}/"
    return {path[len(prefix):] for path in files if path.startswith(prefix)}


def _is_tracked(warning: str, tracked: set[str]) -> bool:
    """True when the file a warning names is git-tracked.

    Both warning shapes lead with the subject and separate it from the reason
    with ``": "``. An atomic warning names a path relative to the memories
    directory; a domain-index warning names a bare file name, which sits at the
    top level of that directory and so compares against the same set.
    """
    subject, _, _ = warning.partition(": ")
    return subject in tracked


def _collect(repo_root: Path) -> list[str] | None:
    """Tracked-file warnings from one healthy scan, or None when unusable."""
    warnings = _warning_lines(repo_root)
    if warnings is None:
        return None
    tracked = _tracked_relative_paths(repo_root)
    if tracked is None:
        return None
    return [w for w in warnings if _is_tracked(w, tracked)]


def current_count(repo_root: Path) -> int | None:
    """Tracked memories that no index references, or None if the scan failed."""
    warnings = _collect(repo_root)
    return None if warnings is None else len(warnings)


def list_violations(
    repo_root: Path, priority_paths: frozenset[str] = frozenset()
) -> list[str] | None:
    """One human-readable line per unindexed memory, or None when unreadable.

    Violations under ``priority_paths`` come first. ``run`` caps the printed
    list at 40 lines and this repository carries several hundred, so emission
    order alone would bury the branch's own violation below the cap.

    ``priority_paths`` holds repository-relative paths while a warning names a
    path relative to the memories directory, so the subject is re-prefixed
    before the comparison.
    """
    warnings = _collect(repo_root)
    if warnings is None:
        return None
    hot: list[str] = []
    rest: list[str] = []
    for warning in warnings:
        subject, _, _ = warning.partition(": ")
        target = hot if f"{_MEMORIES_DIR}/{subject}" in priority_paths else rest
        target.append(warning)
    return hot + rest


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(
        "Whole-repo unindexed-memory count ratchet (issue #4313).", _BASELINE_PATH
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return run(
        args,
        label="memory index count ratchet",
        counter=current_count,
        scan_error="validate_memory_tier.py failed to run",
        regression_advice=(
            "A new memory that no index references cannot merge. Add it to the "
            "matching .serena/memories/skills-<domain>-index.md, or to an "
            "existing domain index, so the retrieval path AGENTS.md points at "
            "can reach it (issue #4313)."
        ),
        lister=list_violations,
    )


if __name__ == "__main__":
    sys.exit(main())
