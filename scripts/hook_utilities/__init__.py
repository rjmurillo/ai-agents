"""Hook utilities package for Claude Code hook scripts."""

from __future__ import annotations

from scripts.hook_utilities.utilities import (
    get_project_directory,
    get_today_session_log,
    get_today_session_logs,
    is_git_commit_command,
)

__all__ = [
    "get_project_directory",
    "get_today_session_log",
    "get_today_session_logs",
    "is_git_commit_command",
]
