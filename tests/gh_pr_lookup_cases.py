"""Shared gh pull request lookup failures and the ADR-035 code each maps to.

A PR script that reads ``gh pr view`` must exit 3 when the PR does not exist
(ADR-035 external error) and 3 for any other failure, including a missing
repository. Exit 2 stays reserved for usage and config errors.
"""

from __future__ import annotations

import pytest

# gh stderr for `gh pr view 999999 --repo rjmurillo/ai-agents`, captured live.
GH_MISSING_PR = (
    "GraphQL: Could not resolve to a PullRequest with the number of 999999. "
    "(repository.pullRequest)\n"
)
GH_MISSING_REPO = "GraphQL: Could not resolve to a Repository with the name 'o/r'. (repository)"

# (stdout, stderr, expected exit code) for one failed `gh pr view`.
PR_VIEW_FAILURE_CASES = [
    pytest.param("", GH_MISSING_PR, 3, id="gh-missing-pr"),
    pytest.param(GH_MISSING_PR, "", 3, id="marker-on-stdout-fallback"),
    pytest.param("", "not found", 3, id="legacy-wording"),
    pytest.param("", "gh: Not Found (HTTP 404)", 3, id="legacy-any-case"),
    pytest.param("", "HTTP 502: Bad Gateway", 3, id="external-error"),
    pytest.param("", GH_MISSING_REPO, 3, id="missing-repo"),
]
