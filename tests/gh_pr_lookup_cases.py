"""Shared gh pull request lookup failures and how each one must classify.

A PR script that reads ``gh pr view`` exits 3 for every lookup failure
(ADR-035 external error). Exit 2 stays reserved for usage and config errors.
Since exit 3 alone cannot tell a missing PR from an outage, each case also
says whether the script must report it as not-found. A consumer asserts that
signal too, so a broken classifier fails in both directions.
"""

from __future__ import annotations

import pytest

# gh stderr for `gh pr view 999999 --repo rjmurillo/ai-agents`, captured live.
GH_MISSING_PR = (
    "GraphQL: Could not resolve to a PullRequest with the number of 999999. "
    "(repository.pullRequest)\n"
)
GH_MISSING_REPO = "GraphQL: Could not resolve to a Repository with the name 'o/r'. (repository)"

# (stdout, stderr, reported as not-found) for one failed `gh pr view`; exit is 3.
PR_VIEW_FAILURE_CASES = [
    pytest.param("", GH_MISSING_PR, True, id="gh-missing-pr"),
    pytest.param(GH_MISSING_PR, "", True, id="marker-on-stdout-fallback"),
    pytest.param("", "not found", True, id="legacy-wording"),
    pytest.param("", "gh: Not Found (HTTP 404)", True, id="legacy-any-case"),
    pytest.param("", "HTTP 502: Bad Gateway", False, id="external-error"),
    pytest.param("", GH_MISSING_REPO, False, id="missing-repo"),
]
