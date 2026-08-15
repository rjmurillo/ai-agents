#!/usr/bin/env python3
"""Block Serena write operations when project scope differs from active worktree.

Issue #4917: Serena edits target the primary checkout even when the session
operates from an external worktree. This guard detects the mismatch and blocks
mutating Serena tools, forcing the user to re-activate the correct project.

Hook Type: PreToolUse
Matcher: ^serena-

Exit Codes (Claude Hook Semantics):
    0 = Allow (read-only tool, or scope matches)
    2 = Block (write tool and scope mismatch)

Fail-open: Infrastructure errors (no git, no .serena/) allow the call.
The guard cannot prove a mismatch when it cannot determine both paths.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_MAX_STDIN_BYTES = 128 * 1024

# Serena tools that mutate files. Only these are blocked on scope mismatch.
_WRITE_TOOLS: frozenset[str] = frozenset(
    {
        "serena-replace_content",
        "serena-replace_symbol_body",
        "serena-insert_before_symbol",
        "serena-insert_after_symbol",
        "serena-replace_in_files",
        "serena-safe_delete_symbol",
        "serena-rename_symbol",
    }
)

# Marker file that identifies the Serena project root.
_SERENA_MARKER = ".serena/project.yml"


def _git_toplevel(cwd: Path) -> Path | None:
    """Return git worktree toplevel for *cwd*, or None on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).resolve()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _serena_project_root() -> Path | None:
    """Determine Serena's active project root.

    Strategy:
    1. SERENA_PROJECT_ROOT env var (explicit override for worktree switching)
    2. Walk up from CLAUDE_PROJECT_DIR (or CWD) looking for .serena/project.yml
    """
    explicit = os.environ.get("SERENA_PROJECT_ROOT", "").strip()
    if explicit:
        p = Path(explicit).resolve()
        if (p / _SERENA_MARKER).is_file():
            return p

    # Walk up from project dir
    start = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    current = Path(start).resolve() if start else Path.cwd().resolve()
    while True:
        if (current / _SERENA_MARKER).is_file():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _read_payload() -> tuple[str, Path]:
    """Read and parse the hook stdin payload. Returns (tool_name, cwd)."""
    if sys.stdin.isatty():
        return "", Path.cwd().resolve()
    raw = sys.stdin.read(_MAX_STDIN_BYTES + 1)
    if len(raw) > _MAX_STDIN_BYTES or not raw.strip():
        return "", Path.cwd().resolve()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return "", Path.cwd().resolve()
    if not isinstance(payload, dict):
        return "", Path.cwd().resolve()

    tool_name = payload.get("tool_name") or payload.get("toolName") or ""

    cwd_value = payload.get("cwd")
    if isinstance(cwd_value, str) and cwd_value.strip():
        cwd = Path(cwd_value)
        if not cwd.is_absolute():
            cwd = Path.cwd() / cwd
        cwd = cwd.resolve()
    else:
        cwd = Path.cwd().resolve()

    return tool_name, cwd


def main() -> int:
    """Entry point. Returns 0 (allow) or 2 (block)."""
    tool_name, cwd = _read_payload()

    # Only gate write tools
    if tool_name not in _WRITE_TOOLS:
        return 0

    # Determine worktree toplevel
    worktree_root = _git_toplevel(cwd)
    if worktree_root is None:
        # Cannot determine worktree; fail open
        return 0

    # Determine Serena project root
    serena_root = _serena_project_root()
    if serena_root is None:
        # Cannot determine Serena root; fail open
        return 0

    # Compare paths
    if worktree_root == serena_root:
        return 0

    # Scope mismatch: block
    print(
        f"Serena worktree scope mismatch (issue #4917).\n"
        f"  Active worktree: {worktree_root}\n"
        f"  Serena project:  {serena_root}\n"
        f"Re-activate Serena for the correct worktree, or set\n"
        f"  SERENA_PROJECT_ROOT={worktree_root}\n"
        f"to override.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
