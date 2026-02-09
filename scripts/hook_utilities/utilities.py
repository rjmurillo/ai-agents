"""Shared utilities for Claude Code hook scripts.

Migrated from .claude/hooks/Common/HookUtilities.psm1 per issue #1053.
"""

from __future__ import annotations

import os
import re
import warnings
from datetime import UTC, datetime
from pathlib import Path

_GIT_COMMIT_PATTERN = re.compile(r"(?:^|\s)git\s+(commit|ci)")


def get_project_directory() -> str:
    """Resolve the project root directory. Never returns None."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if env_dir:
        return env_dir

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


def get_today_session_log(sessions_dir: str, date: str | None = None) -> Path | None:
    """Find the most recent session log for the given date.

    Returns the path with the latest modification time, or None if no logs found.
    """
    if date is None:
        date = datetime.now(tz=UTC).strftime("%Y-%m-%d")

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
