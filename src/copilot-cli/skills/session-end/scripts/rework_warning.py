"""Rework warning detection for session-end (REQ-009-07, REQ-009-08, REQ-009-09).

Surfaces files edited >= ``REWORK_THRESHOLD`` times in the current branch's
commit history. PR #1965 had scan.py touched 56 times before submission and
no tooling surfaced the rework signal. Threshold-6 is a starter calibration
documented in DESIGN-009; kill-criteria pattern (review at 30 invocations)
mirrors the Step 0 gate calibration from REQ-006-13.

Excluded patterns are generated artifacts that legitimately turn over many
times per session (the session log itself, agent-generated copies under
``src/claude/``, and other session JSON files). Counting them as rework
would drown the signal in noise.

This module is the implementation behind the rework-warning emit step in
``complete_session_log.py``. It is extracted into a sibling module so the
parent script stays under the 500-line taste-lint threshold.

Canonical source for the git argv: ``git log --name-only --diff-filter=R
-M origin/{base}..HEAD --pretty=format:``. The rename-detection flag (-M)
is required so a file renamed mid-branch is counted once, not twice.

Exit codes follow ADR-035; functions in this module never exit. They
degrade to an empty list on git failure so callers do not need to wrap
calls in try/except.
"""

from __future__ import annotations

import subprocess
from collections import Counter

REWORK_THRESHOLD = 6
REWORK_EXCLUDED_SUFFIXES = (".session.json",)
REWORK_EXCLUDED_PREFIXES = ("src/claude/", ".agents/sessions/")


def _is_excluded_rework_path(path: str) -> bool:
    """Return True if `path` matches a generated-artifact exclusion pattern."""
    return any(path.endswith(suffix) for suffix in REWORK_EXCLUDED_SUFFIXES) or any(
        path.startswith(prefix) for prefix in REWORK_EXCLUDED_PREFIXES
    )


def _collapse_rename(line: str) -> str:
    """Normalize a git `--name-only -M` rename line to the new path.

    git emits renames in two forms:
        - ``old_path => new_path``
        - ``{old_dir => new_dir}/filename``
    Both collapse to the new path so the file is counted once.

    Lines without `=>` are returned unchanged. The trailing whitespace is
    stripped; a leading slash (rare) is removed for path consistency.
    """
    if "=>" not in line:
        return line
    if line.startswith("{") and "}" in line:
        head, _, tail = line.partition("}")
        new_dir_section = head.split("=>", 1)[1].strip().lstrip("{").strip()
        new_path = f"{new_dir_section}{tail}"
    else:
        new_path = line.split("=>", 1)[1].strip()
    return new_path.lstrip("/").rstrip()


def compute_rework_warning(
    branch_base: str = "main",
    threshold: int = REWORK_THRESHOLD,
) -> list[tuple[str, int]]:
    """Return files edited >= `threshold` times on this branch vs `branch_base`.

    Canonical source: ``git log --name-only --diff-filter=R -M
    origin/{branch_base}..HEAD --pretty=format:`` (rename-aware).

    The ``--diff-filter=R`` flag combined with ``-M`` enables rename
    detection so a file renamed mid-branch is counted as one logical
    file, not two. The ``--pretty=format:`` empty format suppresses the
    commit header so output lines are file paths only.

    Returns a list of ``(file_path, count)`` tuples for files at or above
    the threshold, sorted by count descending then by path ascending for
    deterministic output.

    Degrades gracefully:
      - Git not available -> returns ``[]``
      - Branch base not reachable (e.g. fresh clone) -> returns ``[]``
      - Empty output (no commits ahead of base) -> returns ``[]``

    Stricter/looser/different than canonical:
      - This is a NEW check; there is no upstream validator to mirror.
      - Threshold-6 is local-only; kill-criteria pattern documented inline.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                "--name-only",
                "--diff-filter=R",
                "-M",
                f"origin/{branch_base}..HEAD",
                "--pretty=format:",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0:
        return []

    counts: Counter[str] = Counter()
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = _collapse_rename(line)
        if _is_excluded_rework_path(line):
            continue
        counts[line] += 1

    over_threshold = [
        (path, count) for path, count in counts.items() if count >= threshold
    ]
    over_threshold.sort(key=lambda item: (-item[1], item[0]))
    return over_threshold


def emit_rework_warning_lines(items: list[tuple[str, int]]) -> list[str]:
    """Render rework-warning output lines (REQ-009-07, REQ-009-08).

    Returns at least one line. Empty input yields ``["rework-warning: none"]``
    so absence of a warning is positive evidence the check ran, not silence.
    """
    if not items:
        return ["rework-warning: none"]
    return [f"rework-warning: {path} edited {count} times" for path, count in items]
