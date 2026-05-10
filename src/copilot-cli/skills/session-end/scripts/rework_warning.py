"""Rework warning detection for session-end (REQ-010).

Surfaces files edited >= ``REWORK_THRESHOLD`` times in the current branch's
commit history against ``origin/{branch_base}``. Threshold-6 is empirically
correct per the REQ-010 calibration: real rework files cluster at 8-19 edits
across observed branches; non-rework at 1-4. Threshold-6 separates the two.

Excluded patterns are generated artifacts that legitimately turn over many
times per session and would swamp real signal otherwise:

- ``.agents/sessions/`` — session JSON logs
- ``.agents/memory/episodes/`` — episode logs (added per REQ-010-02 after
  the orphan-ref-validator branch surfaced episode log churn at 19 edits)
- ``src/claude/`` — generated agent copies
- ``*.session.json`` — top-level session JSON files

Canonical source for the git argv: ``git log --name-only -M
origin/{base}..HEAD --pretty=format:``. The ``-M`` flag enables rename
detection so a file renamed mid-branch counts once. ``--diff-filter=R``
is deliberately omitted (would restrict to renames only).

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


def _collapse_rename(line: str) -> str:
    """Normalize a git `--name-only -M` rename line to the new path.

    git emits renames in four shapes; all collapse to the new path:
      - ``old_path => new_path``
      - ``{old_dir => new_dir}/filename``
      - ``path/{old_file => new_file}``
      - ``path/{old_subdir => new_subdir}/filename``
    """
    if "=>" not in line:
        return line.rstrip()
    if "{" in line and "}" in line:
        brace_open = line.index("{")
        brace_close = line.index("}", brace_open)
        prefix = line[:brace_open]
        inside = line[brace_open + 1 : brace_close]
        suffix = line[brace_close + 1 :]
        new_inside = inside.split("=>", 1)[1].strip()
        new_path = f"{prefix}{new_inside}{suffix}"
    else:
        new_path = line.split("=>", 1)[1].strip()
    while "//" in new_path:
        new_path = new_path.replace("//", "/")
    return new_path.lstrip("/").rstrip()


def compute_rework_warning(
    branch_base: str = "main",
    threshold: int = REWORK_THRESHOLD,
) -> list[tuple[str, int]]:
    """Return files edited >= `threshold` times on this branch vs `branch_base`.

    Sorted by count descending then path ascending. Degrades to ``[]`` on
    git failure or missing base ref.
    """
    argv = [
        "git",
        "log",
        "--name-only",
        "-M",
        f"origin/{branch_base}..HEAD",
        "--pretty=format:",
    ]
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=30, check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []

    counts: Counter[str] = Counter()
    for raw in result.stdout.splitlines():
        line = _collapse_rename(raw.strip())
        if line and not _is_excluded_rework_path(line):
            counts[line] += 1

    over = [(p, c) for p, c in counts.items() if c >= threshold]
    over.sort(key=lambda item: (-item[1], item[0]))
    return over


def emit_rework_warning_lines(items: list[tuple[str, int]]) -> list[str]:
    """Render rework-warning output lines.

    Empty input yields ``["rework-warning: none"]`` so absence of a
    warning is positive evidence the check ran, not silence.
    """
    if not items:
        return ["rework-warning: none"]
    return [f"rework-warning: {path} edited {count} times" for path, count in items]
