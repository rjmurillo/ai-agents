"""GitHub Core library for skill scripts.

Shared utilities for GitHub CLI operations:
- Repository inference from git remote
- GitHub CLI authentication check
- GraphQL and REST API helpers
- Input validation (CWE-78, CWE-22 prevention)
- Structured error handling with ADR-035 exit codes

Exit codes (ADR-035):
    0 = Success
    1 = Invalid parameters / specific failure
    2 = Not found
    3 = API error
    4 = Authentication error
    7 = Timeout
"""

from github_core.api import (
    assert_gh_authenticated,
    get_repo_info,
    gh_api_paginated,
    gh_graphql,
    resolve_repo_params,
    write_error_and_exit,
)
from github_core.validation import test_github_name_valid, test_safe_file_path

__all__ = [
    "assert_gh_authenticated",
    "get_repo_info",
    "gh_api_paginated",
    "gh_graphql",
    "resolve_repo_params",
    "test_github_name_valid",
    "test_safe_file_path",
    "write_error_and_exit",
]
