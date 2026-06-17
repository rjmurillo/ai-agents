"""Canonical: scripts/hook_utilities/utilities.py. Sync via scripts/sync_plugin_lib.py.

Migrated from .claude/hooks/Common/HookUtilities.psm1 per issue #1053.

Bootstrap path resolution lives in ``scripts/hook_utilities/bootstrap.py``
(canonical) and its synced copy at ``.claude/lib/bootstrap.py``. Hooks
import from there, not from this module.
"""

from __future__ import annotations

import os
import re
import sys
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_GIT_COMMIT_PATTERN = re.compile(r"(?:^|\s)git\s+(commit|ci)")
_GIT_PUSH_PATTERN = re.compile(r"(?:^|\s)git\s+push(?:\s|$)")
# M7-T3: `gh pr create` dispatches to session_log_guard alongside `git commit`.
# Hooks registered for both commands need to recognize both.
_GH_PR_CREATE_PATTERN = re.compile(r"(?:^|\s)gh\s+pr\s+create\b")
_DATE_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}")

# Cross-platform file locking
# Windows: msvcrt.locking is byte-position-aware and only locks 1 byte at the
# CURRENT file position. For files opened in append mode, each process has its
# own EOF, so locking "at the current position" locks DIFFERENT bytes per
# process and provides no mutual exclusion. Always lock byte 0 (a fixed point
# all processes can contend for), then restore the original write position.
_win_lock_positions: dict[int, int] = {}

if sys.platform == "win32":
    import msvcrt

    def lock_file(f) -> None:
        """Acquire an exclusive lock on a file (Windows implementation)."""
        fd = f.fileno()
        _win_lock_positions[fd] = f.tell()
        f.seek(0)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        pos = _win_lock_positions.get(fd, 0)
        f.seek(pos)

    def unlock_file(f) -> None:
        """Release an exclusive lock on a file (Windows implementation)."""
        fd = f.fileno()
        write_pos = f.tell()
        f.seek(0)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        _win_lock_positions.pop(fd, None)
        f.seek(write_pos)
else:
    import fcntl

    def lock_file(f) -> None:
        """Acquire an exclusive lock on a file (POSIX implementation)."""
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)

    def unlock_file(f) -> None:
        """Release an exclusive lock on a file (POSIX implementation)."""
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def get_project_directory() -> str:
    """Resolve the project root directory. Never returns None."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        return str(Path(env_dir).resolve())

    # Walk up from cwd looking for .git
    try:
        current = Path.cwd().resolve()
        while True:
            if (current / ".git").exists():
                return str(current)
            parent = current.parent
            if parent == current:
                break
            current = parent
    except OSError as exc:
        warnings.warn(
            f"Failed to locate project directory: {exc}. Using current directory as fallback.",
            stacklevel=2,
        )
        return str(Path.cwd())

    warnings.warn(
        "Project root (.git directory) not found. Using current directory as fallback.",
        stacklevel=2,
    )
    return str(Path.cwd())


def is_git_commit_command(command: str | None) -> bool:
    """Check if a command string is a git commit or git ci command."""
    if not command:
        return False
    return _GIT_COMMIT_PATTERN.search(command) is not None


def is_git_push_command(command: str | None) -> bool:
    """Check if a command string is a git push command."""
    if not command:
        return False
    return _GIT_PUSH_PATTERN.search(command) is not None


def is_git_commit_or_push_command(command: str | None) -> bool:
    """Check if a command string is a git commit, ci, or push command."""
    return is_git_commit_command(command) or is_git_push_command(command)


def is_pr_create_command(command: str | None) -> bool:
    """Check if a command string creates a GitHub pull request via the gh CLI.

    M7-T3: hooks registered for both `Bash(git commit*)` and the
    pr-creation matcher need to recognize both. Without this, the
    pr-creation copy of session_log_guard fires its shim correctly but
    the body returns immediately because it only checked git commit.
    """
    if not command:
        return False
    return _GH_PR_CREATE_PATTERN.search(command) is not None


def is_session_logged_command(command: str | None) -> bool:
    """True for any command that requires a session log to exist (git commit or pr create).

    Aggregates :func:`is_git_commit_command` and :func:`is_pr_create_command`
    so multi-matcher hooks have a single predicate to call regardless of
    which matcher fired the shim.
    """
    return is_git_commit_command(command) or is_pr_create_command(command)


def get_today_session_log(sessions_dir: str, date: str | None = None) -> Path | None:
    """Find the most recent session log for the given date.

    Returns the path with the latest modification time, or None if no logs found.
    """
    if date is None:
        date = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    elif not _DATE_FORMAT.fullmatch(date):
        msg = f"Invalid date format: {date!r}. Expected YYYY-MM-DD."
        raise ValueError(msg)

    sessions_path = Path(sessions_dir)
    if not sessions_path.is_dir():
        warnings.warn(f"Session directory not found: {sessions_dir}", stacklevel=2)
        return None

    try:
        logs = sorted(
            sessions_path.glob(f"{date}-session-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError as exc:
        warnings.warn(
            f"Failed to read session logs from {sessions_dir}: {exc}",
            stacklevel=2,
        )
        return None

    if not logs:
        return None
    return logs[0]


def _newest_by_mtime(candidates: list[Path]) -> Path | None:
    """Return newest candidate by mtime, skipping ones whose stat fails.

    A single transient stat failure (race with deletion/rename, permission
    issue) on one candidate must not blind the caller to the rest. Skip
    unreadable entries and pick the newest of those that stat successfully.
    """
    best: Path | None = None
    best_mtime = float("-inf")
    for candidate in candidates:
        try:
            mtime = candidate.stat().st_mtime
        except OSError as exc:
            warnings.warn(
                f"Skipping unreadable session log {candidate}: {exc}",
                stacklevel=2,
            )
            continue
        if mtime > best_mtime:
            best_mtime = mtime
            best = candidate
    return best


def get_today_session_logs(sessions_dir: str) -> list[Path]:
    """Find all session logs for today's date."""
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    sessions_path = Path(sessions_dir)
    if not sessions_path.is_dir():
        warnings.warn(f"Session directory not found: {sessions_dir}", stacklevel=2)
        return []

    try:
        return list(sessions_path.glob(f"{today}-session-*.json"))
    except OSError as exc:
        warnings.warn(
            f"Failed to read session logs from {sessions_dir}: {exc}",
            stacklevel=2,
        )
        return []


def get_recent_session_log(sessions_dir: str) -> Path | None:
    """Find the most recent session log for the current session.

    Returns the newest today-prefixed session log when any today candidate
    stats successfully. Falls back to the newest yesterday-prefixed session
    log in two cases: (1) no today-prefixed file exists at all, and (2) today
    candidates exist but every one of them fails stat() (a transient FS error
    or race). The fallback supports sessions that span midnight and prevents
    a single transient stat failure from blinding hooks to the session.
    """
    sessions_path = Path(sessions_dir)
    if not sessions_path.is_dir():
        warnings.warn(f"Session directory not found: {sessions_dir}", stacklevel=2)
        return None

    now = datetime.now(tz=UTC)
    today = now.strftime("%Y-%m-%d")

    # First, check for today's sessions
    try:
        today_candidates = list(sessions_path.glob(f"{today}-session-*.json"))
    except OSError as exc:
        warnings.warn(
            f"Failed to read session logs from {sessions_dir}: {exc}",
            stacklevel=2,
        )
        return None

    most_recent = _newest_by_mtime(today_candidates)
    if most_recent is not None:
        return most_recent
    if today_candidates:
        # All today candidates errored on stat. Fall through to yesterday so a
        # single transient stat failure does not blind hooks to the session.
        warnings.warn(
            "All today session logs failed stat; falling back to yesterday",
            stacklevel=2,
        )

    # Only fall back to yesterday if no today session exists (cross-midnight continuation)
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        yesterday_candidates = list(sessions_path.glob(f"{yesterday}-session-*.json"))
    except OSError as exc:
        warnings.warn(
            f"Failed to read session logs from {sessions_dir}: {exc}",
            stacklevel=2,
        )
        return None

    return _newest_by_mtime(yesterday_candidates)


def coerce_to_list(value) -> list[Any]:
    """Normalize work/outcomes to a list, regardless of session schema shape.

    Session logs in this repo have used several shapes over time:
    - ``work: [...]`` (legacy flat list)
    - ``work: {tasks: [...]}`` / ``{items: [...]}`` (dict wrapper)
    - ``workLog: [...]`` (current schema)
    - bare strings (rare)

    Returns an empty list for None or unrecognized types.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if not value:
            # Empty dict (e.g., outcomes: {}) is "no items", not one item.
            # Fixes is_trivial_session false-negative on empty schema objects.
            return []
        for key in ("tasks", "items", "log", "entries"):
            inner = value.get(key)
            if isinstance(inner, list):
                return inner
        for v in value.values():
            if isinstance(v, list):
                return v
        return [value]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return []


def format_work_item(item: dict[str, Any]) -> str:
    """Format a work item dict into a human-readable string.

    Supports multiple session schemas:
    - Current: {'step': N, 'action': '...', 'outcome': '...'}
    - Legacy: {'description': '...'} or {'task': '...'}
    """
    if "action" in item:
        parts = []
        if "step" in item:
            parts.append(f"Step {item['step']}:")
        parts.append(str(item["action"]))
        if "outcome" in item:
            parts.append(f"→ {item['outcome']}")
        return " ".join(parts)
    if "description" in item:
        return str(item["description"])
    if "task" in item:
        return str(item["task"])
    return str(item)
