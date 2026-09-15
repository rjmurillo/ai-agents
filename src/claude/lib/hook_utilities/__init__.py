"""Hook utilities package for Claude Code hook scripts.

NOTE: Plugin-distributed copies are generated into the plugin trees.
Run ``uv run python build/scripts/build_all.py`` to regenerate them.
"""

from __future__ import annotations

from .guards import (
    is_project_repo,
    skip_if_consumer_repo,
)
from .utilities import (
    coerce_to_list,
    format_work_item,
    get_project_directory,
    get_recent_session_log,
    get_today_session_log,
    get_today_session_logs,
    is_git_commit_command,
    is_git_push_command,
    is_pr_create_command,
    lock_file,
    unlock_file,
)

__all__ = [
    "coerce_to_list",
    "format_work_item",
    "get_project_directory",
    "get_recent_session_log",
    "get_today_session_log",
    "get_today_session_logs",
    "is_git_commit_command",
    "is_git_push_command",
    "is_pr_create_command",
    "is_project_repo",
    "lock_file",
    "skip_if_consumer_repo",
    "unlock_file",
]
