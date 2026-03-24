"""Canonical: scripts/hook_utilities/__init__.py. Sync via scripts/sync_plugin_lib.py.

NOTE: Plugin-distributed copy at .claude/lib/hook_utilities/.
Run ``python3 scripts/sync_plugin_lib.py`` to sync changes.
"""

from __future__ import annotations

from .guards import (
    is_project_repo,
    skip_if_consumer_repo,
)
from .utilities import (
    get_project_directory,
    get_today_session_log,
    get_today_session_logs,
    is_git_commit_command,
    is_git_commit_or_push_command,
    is_git_push_command,
)

__all__ = [
    "get_project_directory",
    "get_today_session_log",
    "get_today_session_logs",
    "is_git_commit_command",
    "is_git_commit_or_push_command",
    "is_git_push_command",
    "is_project_repo",
    "skip_if_consumer_repo",
]
