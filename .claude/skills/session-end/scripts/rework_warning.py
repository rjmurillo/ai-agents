"""Rework warning detection for session-end (REQ-012-07, REQ-012-08, REQ-012-09, REQ-010, REQ-010-02).

Surfaces files edited >= ``REWORK_THRESHOLD`` times in the current branch's
commit history. PR #1965 had scan.py touched 56 times before submission and
no tooling surfaced the rework signal. Threshold-6 is empirically correct per
the REQ-010 calibration: real rework files cluster at 8-19 edits across observed
branches; non-rework at 1-4. Kill-criteria pattern (review at 30 invocations)
mirrors the Step 0 gate calibration from REQ-006-13.

Excluded patterns are generated artifacts that legitimately turn over many
times per session and would swamp real signal otherwise:

- ``.agents/sessions/`` session JSON logs
- ``.agents/memory/episodes/`` episode logs (added per REQ-010-02 after
  the orphan-ref-validator branch surfaced episode log churn at 19 edits)
- ``src/claude/`` generated agent copies
- ``*.session.json`` top-level session JSON files

This module is the implementation behind the rework-warning emit step in
``complete_session_log.py``. It is extracted into a sibling module so the
parent script stays under the 500-line taste-lint threshold.

Canonical source for the git argv: ``git log --name-status -M
origin/{base}..HEAD --pretty=format:``. The rename-detection flag (-M)
combined with ``--name-status`` enables proper rename tracking: the
status output includes ``R<score>\\told\\tnew`` lines that let us build
a rename mapping so a file renamed mid-branch is counted once, not twice.
NOTE: ``--diff-filter=R`` is deliberately omitted; it would restrict
output to RENAMED files only and miss all ordinary edits (M/A). The
fix landed after PR #1989 bot reviewers flagged the broken signal.

Exit codes follow ADR-035; functions in this module never exit. They
degrade to an empty list on git failure so callers do not need to wrap
calls in try/except.
"""

from __future__ import annotations

import subprocess
from collections import Counter

REWORK_THRESHOLD = 6

# REQ-010-02: episode logs added to exclusion list. PR #1995 calibration
# showed episode.json files at 19 edits/branch swamping real signal.
_REWORK_EXCLUDED_SUFFIXES = (".session.json",)
_REWORK_EXCLUDED_PREFIXES = (
    "src/claude/",
    ".agents/sessions/",
    ".agents/memory/episodes/",
)


def _is_excluded_rework_path(path: str) -> bool:
    """Return True if `path` matches a generated-artifact exclusion pattern."""
    return any(path.endswith(suffix) for suffix in _REWORK_EXCLUDED_SUFFIXES) or any(
        path.startswith(prefix) for prefix in _REWORK_EXCLUDED_PREFIXES
    )


_GIT_LOG_ARGV = (
    "git",
    "log",
    "--name-status",
    "-M",
    "{base_ref}",
    "--pretty=format:",
)


def _run_git_log(branch_base: str) -> str | None:
    """Run canonical ``git log --name-status -M`` against base.

    Reports ALL file edits (Modified, Added, Renamed) with status codes.
    The ``-M`` flag enables rename detection; ``--name-status`` outputs
    ``R<score>\\told\\tnew`` for renames, allowing proper rename mapping.
    ``--diff-filter=R`` is NOT used (would restrict to renames only and
    miss ordinary edits; PR #1989 bot review found).
    """
    argv = [a.format(base_ref=f"origin/{branch_base}..HEAD") for a in _GIT_LOG_ARGV]
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=30, check=False
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _count_paths(stdout: str) -> Counter[str]:
    """Tally per-path edit counts, collapsing renames, excluding generated.

    With ``--name-status -M``, git outputs tab-separated lines:
        - ``M\\tpath`` for modifications
        - ``A\\tpath`` for additions
        - ``D\\tpath`` for deletions
        - ``R<score>\\told_path\\tnew_path`` for renames

    First pass builds a rename mapping (old to new), then second pass counts
    paths normalized to their final name so a renamed file is counted once.
    """
    renames: dict[str, str] = {}
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0].startswith("R"):
            old_path, new_path = parts[1], parts[2]
            renames[old_path] = new_path

    def _resolve_final_name(path: str) -> str:
        """Follow rename chain to final name, handling cycles."""
        visited: set[str] = set()
        while path in renames and path not in visited:
            visited.add(path)
            path = renames[path]
        return path

    counts: Counter[str] = Counter()
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split("\t")
        # str.split always returns >=1 element on a non-empty string, so
        # parts is never empty here; no defensive empty-list branch.
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:
            path = _resolve_final_name(parts[2])
        elif len(parts) >= 2:
            path = _resolve_final_name(parts[1])
        else:
            # Malformed git output: status token with no path. Skip.
            continue
        if path and not _is_excluded_rework_path(path):
            counts[path] += 1
    return counts


def _filter_over_threshold(
    counts: Counter[str], threshold: int
) -> list[tuple[str, int]]:
    """Return ``(path, count)`` >= threshold, sorted by count desc then path asc."""
    over = [(p, c) for p, c in counts.items() if c >= threshold]
    over.sort(key=lambda item: (-item[1], item[0]))
    return over


def compute_rework_warning(
    branch_base: str = "main",
    threshold: int = REWORK_THRESHOLD,
) -> list[tuple[str, int]]:
    """Return files edited >= `threshold` times on this branch.

    Degrades to ``[]`` when git is unavailable, the base is unreachable,
    or no commits are ahead. Threshold-6 is local-only starter calibration
    documented in DESIGN-012; kill-criteria pattern mirrors REQ-006-13.
    """
    stdout = _run_git_log(branch_base)
    if stdout is None:
        return []
    return _filter_over_threshold(_count_paths(stdout), threshold)


def emit_rework_warning_lines(items: list[tuple[str, int]]) -> list[str]:
    """Render rework-warning output lines (REQ-012-07, REQ-012-08).

    Returns at least one line. Empty input yields ``["rework-warning: none"]``
    so absence of a warning is positive evidence the check ran, not silence.
    """
    if not items:
        return ["rework-warning: none"]
    return [f"rework-warning: {path} edited {count} times" for path, count in items]
