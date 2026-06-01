"""Hook utilities package for Claude Code hook scripts.

NOTE: Plugin-distributed copy at .claude/lib/hook_utilities/.
Run ``python3 scripts/sync_plugin_lib.py`` to sync changes.
"""

from __future__ import annotations

from scripts.hook_utilities.guards import (
    is_project_repo,
    skip_if_consumer_repo,
)
from scripts.hook_utilities.lsp_gate_state import (
    FREE_READS,
    NAV_REQUIRED,
    WARN_AT,
    is_gated_target,
    normalize_path,
    read_state,
    record_nav,
    record_read,
    record_warmup,
    reset_state,
    state_path,
    write_state,
)
from scripts.hook_utilities.lsp_provider import (
    PROVIDERS,
    SYMBOL_NAVIGATION,
    SYMBOLS_OVERVIEW,
    detect_providers,
    is_code_target,
)
from scripts.hook_utilities.lsp_symbols import (
    extract_pattern_and_target,
    is_code_symbol,
    is_git_grep,
    is_grep_search,
    strip_zero_width,
)
from scripts.hook_utilities.utilities import (
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
    "is_gated_target",
    "is_grep_search",
    "is_pr_create_command",
    "is_project_repo",
    "is_session_logged_command",
    "lock_file",
    "normalize_path",
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
