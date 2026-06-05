#!/usr/bin/env python3
"""Verify no leftover merge-conflict markers remain after a merge resolution.

Used by the merge-resolver skill (Phase 3 validation) and during local
verification before pushing a resolved branch. Replaces the broad
``git grep -n '<<<<<<<' --`` recommendation, which false-fails on
intentional fenced ``<<<<<<<`` examples in documentation and Serena
memory files (issue #2424).

Strategy
--------

This script checks the two states that actually matter after a merge
resolution, using git plumbing instead of full-tree text search:

1. ``git diff --name-only --diff-filter=U`` -- still-unmerged (UU)
   files. If any are listed, the merge isn't fully staged yet.

2. ``git diff HEAD --check`` -- ``git diff --check`` extended to
   compare HEAD against working tree + index. ``--check`` is the
   built-in primitive for "look for leftover conflict markers" and
   reports them with file:line precision. It only inspects in-flight
   changes, so committed historical content (the intentional fenced
   examples in ``.claude/skills/merge-resolver/references/strategies.md``
   and ``.serena/memories/patterns/pattern-handoff-merge-session-histories.md``)
   is intentionally ignored.

Together these catch every real leftover-marker scenario:

- markers in unstaged working tree (post-merge, not yet ``git add``-ed),
- markers in staged but not committed changes (``git add`` after
  partial resolution),
- files still in unmerged (UU) state,

while never tripping on intentional, already-committed fenced examples
in documentation.

Exit codes follow ADR-035:

    0 -- Clean: no UU files and no leftover conflict markers
    1 -- Validation failed: markers remain or unmerged files exist
    2 -- Usage / configuration error (not in a git repo)
    3 -- External error (git command failed unexpectedly)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _run_git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a git command, capturing stdout/stderr as text.

    Does not raise on non-zero exit; callers interpret returncode.
    """
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )


def _is_in_git_repo(cwd: Path) -> bool:
    """Return True if ``cwd`` is inside a git working tree."""
    result = _run_git(["rev-parse", "--is-inside-work-tree"], cwd=cwd)
    return result.returncode == 0 and result.stdout.strip() == "true"


def list_unmerged_files(cwd: Path) -> list[str]:
    """Return paths of files still in unmerged (UU/AA/DU/etc) state.

    Uses ``git diff --name-only --diff-filter=U`` which is the canonical
    way to enumerate paths that have unresolved conflicts in the index.
    """
    result = _run_git(["diff", "--name-only", "--diff-filter=U"], cwd=cwd)
    if result.returncode != 0:
        # Surface git's stderr to help the caller diagnose.
        raise RuntimeError(
            f"git diff --diff-filter=U failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return [line for line in result.stdout.splitlines() if line.strip()]


def find_leftover_markers(cwd: Path) -> list[str]:
    """Return ``file:line: message`` strings for leftover conflict markers.

    Uses ``git diff HEAD --check`` which reports leftover conflict
    markers in any in-flight change (working tree or index) relative to
    HEAD. Exit code 2 from ``--check`` means markers were found; exit 0
    means none.
    """
    result = _run_git(["diff", "HEAD", "--check"], cwd=cwd)

    # --check returncodes:
    #   0 -- clean
    #   2 -- conflict markers (or other --check problems) were reported
    #   other -- unexpected git failure
    if result.returncode == 0:
        return []
    if result.returncode == 2:
        return [line for line in result.stdout.splitlines() if line.strip()]

    raise RuntimeError(
        f"git diff HEAD --check failed (exit {result.returncode}): {result.stderr.strip()}"
    )


def verify(cwd: Path) -> tuple[int, dict[str, object]]:
    """Run the full verification, returning ``(exit_code, report_dict)``."""
    if not _is_in_git_repo(cwd):
        report = {
            "ok": False,
            "error": "not_in_git_repo",
            "cwd": str(cwd),
        }
        return 2, report

    try:
        unmerged = list_unmerged_files(cwd)
        markers = find_leftover_markers(cwd)
    except RuntimeError as exc:
        return 3, {"ok": False, "error": "git_failed", "detail": str(exc)}

    if not unmerged and not markers:
        return 0, {"ok": True, "unmerged_files": [], "leftover_markers": []}

    return 1, {
        "ok": False,
        "unmerged_files": unmerged,
        "leftover_markers": markers,
    }


def _format_human(report: dict[str, object]) -> str:
    """Format the report for human reading."""
    if report.get("ok"):
        return "[ok] no unmerged files and no leftover conflict markers"

    if report.get("error") == "not_in_git_repo":
        return f"[error] not inside a git working tree: {report.get('cwd')}"

    if report.get("error") == "git_failed":
        return f"[error] git command failed: {report.get('detail')}"

    lines = ["[fail] conflict resolution incomplete"]
    unmerged_raw = report.get("unmerged_files") or []
    markers_raw = report.get("leftover_markers") or []
    unmerged: list[str] = list(unmerged_raw) if isinstance(unmerged_raw, list) else []
    markers: list[str] = list(markers_raw) if isinstance(markers_raw, list) else []
    if unmerged:
        lines.append("")
        lines.append(f"  unmerged files ({len(unmerged)}):")
        for path in unmerged:
            lines.append(f"    - {path}")
    if markers:
        lines.append("")
        lines.append(f"  leftover conflict markers ({len(markers)}):")
        for marker in markers:
            lines.append(f"    {marker}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_no_conflict_markers",
        description=(
            "Verify that the working tree has no leftover merge-conflict "
            "markers and no still-unmerged files. Replaces 'git grep' "
            "false-positives on intentional fenced examples."
        ),
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help="Run inside this directory (default: current working directory).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable text.",
    )
    args = parser.parse_args(argv)

    cwd = Path(args.cwd).resolve() if args.cwd else Path.cwd()

    exit_code, report = verify(cwd)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_format_human(report))

    return exit_code


if __name__ == "__main__":  # pragma: no cover - entry-point guard
    sys.exit(main())
