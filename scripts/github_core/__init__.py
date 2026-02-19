"""GitHub Core module: shared helpers for GitHub CLI operations.

NOTE: Plugin-distributed copy at .claude/lib/github_core/.
Run ``python3 scripts/sync_plugin_lib.py`` to sync changes.
"""

from __future__ import annotations

from scripts.github_core.api import (  # noqa: F401
    DEFAULT_RATE_THRESHOLDS,
    RateLimitResult,
    assert_gh_authenticated,
    check_workflow_rate_limit,
    create_issue_comment,
    error_and_exit,
    get_all_prs_with_comments,
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
from scripts.github_core.bot_config import (  # noqa: F401
    get_bot_authors,
    get_bot_authors_config,
)
from scripts.github_core.formatting import (  # noqa: F401
    get_priority_emoji,
    get_reaction_emoji,
)
from scripts.github_core.gh_client import GhCliClient  # noqa: F401
from scripts.github_core.protocol import GitHubClient  # noqa: F401
from scripts.github_core.validation import (  # noqa: F401
    assert_valid_body_file,
    is_github_name_valid,
    is_safe_file_path,
)

__all__ = [
    "DEFAULT_RATE_THRESHOLDS",
    "GhCliClient",
    "GitHubClient",
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
