"""Canonical: scripts/hook_utilities/utilities.py. Sync via scripts/sync_plugin_lib.py.

Migrated from .claude/hooks/Common/HookUtilities.psm1 per issue #1053.
"""

from __future__ import annotations

import os
import re
import sys
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path

_GIT_COMMIT_PATTERN = re.compile(r"(?:^|\s)git\s+(commit|ci)")
_GIT_PUSH_PATTERN = re.compile(r"(?:^|\s)git\s+push(?:\s|$)")
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
    """Find the most recent session log, checking today and yesterday (UTC).

    Sessions that span midnight may have logs dated yesterday, so we check both
    dates and return the most recently modified file.
    """
    sessions_path = Path(sessions_dir)
    if not sessions_path.is_dir():
        warnings.warn(f"Session directory not found: {sessions_dir}", stacklevel=2)
        return None

    now = datetime.now(tz=UTC)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    candidates: list[Path] = []
    try:
        for date_prefix in (today, yesterday):
            candidates.extend(sessions_path.glob(f"{date_prefix}-session-*.json"))
    except OSError as exc:
        warnings.warn(
            f"Failed to read session logs from {sessions_dir}: {exc}",
            stacklevel=2,
        )
        return None

    if not candidates:
        return None

    try:
        return max(candidates, key=lambda f: f.stat().st_mtime)
    except OSError as exc:
        warnings.warn(
            f"Failed to stat session logs: {exc}",
            stacklevel=2,
        )
        return None
