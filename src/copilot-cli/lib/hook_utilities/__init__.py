"""Canonical: scripts/hook_utilities/__init__.py. Sync via scripts/sync_plugin_lib.py.

NOTE: Plugin-distributed copy at .claude/lib/hook_utilities/.
Run ``python3 scripts/sync_plugin_lib.py`` to sync changes.
"""

from __future__ import annotations

from .guards import (
    is_project_repo,
    skip_if_consumer_repo,
)
from .lsp_gate_state import (
    FREE_READS,
    NAV_REQUIRED,
    WARN_AT,
    read_state,
    record_nav,
    record_read,
    record_warmup,
    reset_state,
    state_path,
    write_state,
)
from .lsp_provider import (
    PROVIDERS,
    SYMBOL_NAVIGATION,
    SYMBOLS_OVERVIEW,
    detect_providers,
    is_code_target,
)
from .lsp_symbols import (
    extract_pattern_and_target,
    is_code_symbol,
    is_git_grep,
    is_grep_search,
    strip_zero_width,
)
from .utilities import (
    coerce_to_list,
    format_work_item,
    get_project_directory,
    get_recent_session_log,
    get_today_session_log,
    get_today_session_logs,
    is_git_commit_command,
    is_git_commit_or_push_command,
    is_git_push_command,
    is_pr_create_command,
    is_session_logged_command,
    lock_file,
    unlock_file,
)

__all__ = [
    "FREE_READS",
    "NAV_REQUIRED",
    "PROVIDERS",
    "SYMBOLS_OVERVIEW",
    "SYMBOL_NAVIGATION",
    "WARN_AT",
    "coerce_to_list",
    "detect_providers",
    "extract_pattern_and_target",
    "format_work_item",
    "get_project_directory",
    "get_recent_session_log",
    "get_today_session_log",
    "get_today_session_logs",
    "is_code_symbol",
    "is_code_target",
    "is_git_commit_command",
    "is_git_commit_or_push_command",
    "is_git_grep",
    "is_git_push_command",
    "is_grep_search",
    "is_pr_create_command",
    "is_project_repo",
    "is_session_logged_command",
    "lock_file",
    "read_state",
    "record_nav",
    "record_read",
    "record_warmup",
    "reset_state",
    "skip_if_consumer_repo",
    "state_path",
    "strip_zero_width",
    "unlock_file",
    "write_state",
]
