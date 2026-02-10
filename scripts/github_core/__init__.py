"""GitHub Core module: shared helpers for GitHub CLI operations."""

from __future__ import annotations

from scripts.github_core.api import (
    DEFAULT_RATE_THRESHOLDS,
    RateLimitResult,
    assert_gh_authenticated,
    check_workflow_rate_limit,
    create_issue_comment,
    error_and_exit,
    get_all_prs_with_comments,
    get_bot_authors,
    get_bot_authors_config,
    get_issue_comments,
    get_repo_info,
    get_trusted_source_comments,
    get_unresolved_review_threads,
    gh_api_paginated,
    gh_graphql,
    is_gh_authenticated,
    resolve_repo_params,
    update_issue_comment,
)
from scripts.github_core.formatting import (
    get_priority_emoji,
    get_reaction_emoji,
)
from scripts.github_core.validation import (
    assert_valid_body_file,
    is_github_name_valid,
    is_safe_file_path,
)

__all__ = [
    "DEFAULT_RATE_THRESHOLDS",
    "RateLimitResult",
    "assert_gh_authenticated",
    "assert_valid_body_file",
    "check_workflow_rate_limit",
    "create_issue_comment",
    "error_and_exit",
    "get_all_prs_with_comments",
    "get_bot_authors",
    "get_bot_authors_config",
    "get_issue_comments",
    "get_priority_emoji",
    "get_reaction_emoji",
    "get_repo_info",
    "get_trusted_source_comments",
    "get_unresolved_review_threads",
    "gh_api_paginated",
    "gh_graphql",
    "is_gh_authenticated",
    "is_github_name_valid",
    "is_safe_file_path",
    "resolve_repo_params",
    "update_issue_comment",
]
