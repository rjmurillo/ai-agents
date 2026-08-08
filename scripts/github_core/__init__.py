"""GitHub Core module: shared helpers for GitHub CLI operations.

NOTE: Plugin-distributed copy at .claude/lib/github_core/.
Run ``python3 scripts/sync_plugin_lib.py`` to sync changes.
"""

from __future__ import annotations

from scripts.github_core.api import (
    DEFAULT_RATE_THRESHOLDS,
    FetchStatus,
    GhAuthResult,
    GhAuthStatus,
    RateLimitResult,
    RateLimitStatus,
    RepoInfo,
    assert_gh_authenticated,
    check_gh_auth,
    check_workflow_rate_limit,
    classify_gh_failure_response,
    classify_gh_failure_text,
    count_unresolved_threads,
    create_issue_comment,
    describe_gh_auth_failure,
    error_and_exit,
    filter_unresolved_threads,
    get_all_prs_with_comments,
    get_issue_comments,
    get_repo_info,
    get_trusted_source_comments,
    get_unresolved_review_threads,
    gh_api_paginated,
    gh_graphql,
    is_gh_authenticated,
    resolve_repo_params,
    safe_log_str,
    transform_review_thread,
    update_issue_comment,
)
from scripts.github_core.bot_config import (
    get_bot_authors,
    get_bot_authors_config,
    is_bot,
)
from scripts.github_core.formatting import (
    get_priority_emoji,
    get_reaction_emoji,
)
from scripts.github_core.gh_client import GhCliClient
from scripts.github_core.output import (
    get_output_format,
    write_skill_error,
    write_skill_output,
)
from scripts.github_core.protocol import GitHubClient
from scripts.github_core.repo import (
    REPO_ROOT_GIT_FAILED,
    REPO_ROOT_NOT_A_REPO,
    REPO_ROOT_OK,
    get_repo_root,
    resolve_repo_root,
)
from scripts.github_core.validation import (
    assert_valid_body_file,
    escaped_newline_body_error,
    inline_body_error,
    is_github_name_valid,
    is_safe_file_path,
)

__all__ = [
    "DEFAULT_RATE_THRESHOLDS",
    "FetchStatus",
    "GhAuthResult",
    "GhAuthStatus",
    "GhCliClient",
    "GitHubClient",
    "RateLimitResult",
    "RateLimitStatus",
    "RepoInfo",
    "assert_gh_authenticated",
    "assert_valid_body_file",
    "check_gh_auth",
    "check_workflow_rate_limit",
    "classify_gh_failure_response",
    "classify_gh_failure_text",
    "count_unresolved_threads",
    "create_issue_comment",
    "describe_gh_auth_failure",
    "error_and_exit",
    "escaped_newline_body_error",
    "inline_body_error",
    "filter_unresolved_threads",
    "get_all_prs_with_comments",
    "get_bot_authors",
    "get_bot_authors_config",
    "get_issue_comments",
    "get_output_format",
    "get_priority_emoji",
    "get_reaction_emoji",
    "get_repo_info",
    "REPO_ROOT_GIT_FAILED",
    "REPO_ROOT_NOT_A_REPO",
    "REPO_ROOT_OK",
    "get_repo_root",
    "resolve_repo_root",
    "get_trusted_source_comments",
    "get_unresolved_review_threads",
    "gh_api_paginated",
    "gh_graphql",
    "is_bot",
    "is_gh_authenticated",
    "is_github_name_valid",
    "is_safe_file_path",
    "resolve_repo_params",
    "safe_log_str",
    "transform_review_thread",
    "update_issue_comment",
    "write_skill_error",
    "write_skill_output",
]
