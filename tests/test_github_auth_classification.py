"""Classification of gh failure text and responses (issues #3139, #4344, #4326).

Covers the failure-text and response classifiers and the transport-blocked
cases. Captured refusal bodies live in ``tests/gh_auth_refusal_fixtures.py``.
"""

from __future__ import annotations

import pytest

import scripts.github_core.api as api
from scripts.github_core.api import (
    GhAuthStatus,
    classify_gh_failure_response,
    classify_gh_failure_text,
)
from tests.gh_auth_refusal_fixtures import (
    BAD_CREDENTIALS,
    GH_CONNECT_FAILURE,
    GH_DIAL_FAILURE,
    GH_DNS_FAILURE,
    GRAPHQL_QUOTA,
    PERMISSION_DENIED,
    PROXY_GRAPHQL_403,
    PROXY_REST_403,
    REST_403_QUOTA,
    REST_503,
    REST_BODY_QUOTA,
    RUN_LIST_403_QUOTA,
    SECONDARY_LIMIT,
)


class TestModuleLevelConstantsAreDefinedOnce:
    """A shadowed constant is invisible until someone edits the wrong copy.

    `_RETRYABLE_REFUSAL_STATUSES` was defined twice: once beside `check_gh_auth`
    for the promotion guard and once beside the GraphQL retry ladder. Python
    kept the later one, the values happened to match, and nothing failed. An
    edit to either would have moved both behaviors at once, and only one of
    them would have had a test (Copilot review on PR #5509).
    """

    def test_no_module_level_name_is_assigned_twice(self):
        import ast
        from pathlib import Path as _Path

        source = _Path(api.__file__).read_text(encoding="utf-8")
        seen: dict[str, int] = {}
        duplicates = []
        for node in ast.parse(source).body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                name = getattr(target, "id", None)
                if name is None:
                    continue
                if name in seen:
                    duplicates.append(f"{name} (lines {seen[name]} and {node.lineno})")
                seen[name] = node.lineno

        assert not duplicates, f"shadowed module-level assignments: {duplicates}"


class TestClassifyGhFailureText:
    @pytest.mark.parametrize(
        "body",
        [REST_403_QUOTA, RUN_LIST_403_QUOTA, REST_BODY_QUOTA, GRAPHQL_QUOTA],
    )
    def test_primary_quota_refusal_is_rate_limited(self, body):
        assert classify_gh_failure_text(body) is GhAuthStatus.RATE_LIMITED

    def test_secondary_limit_is_its_own_status(self):
        assert classify_gh_failure_text(SECONDARY_LIMIT) is GhAuthStatus.SECONDARY_RATE_LIMITED

    def test_rate_limit_text_with_remaining_header_is_secondary(self):
        body = f"{REST_403_QUOTA}\nX-Ratelimit-Remaining: 4935"

        assert classify_gh_failure_text(body) is GhAuthStatus.SECONDARY_RATE_LIMITED

    def test_rest_5xx_is_transient(self):
        assert classify_gh_failure_text(REST_503) is GhAuthStatus.TRANSIENT_ERROR

    @pytest.mark.parametrize("body", [GH_DIAL_FAILURE, GH_CONNECT_FAILURE, GH_DNS_FAILURE])
    def test_gh_connectivity_wording_is_transient(self, body):
        """gh's own transport text carries no HTTP status and no curl wording."""
        assert classify_gh_failure_text(body) is GhAuthStatus.TRANSIENT_ERROR

    def test_bad_credentials_is_invalid(self):
        assert classify_gh_failure_text(BAD_CREDENTIALS) is GhAuthStatus.INVALID_CREDENTIALS

    def test_permission_denial_is_not_a_quota_refusal(self):
        assert classify_gh_failure_text(PERMISSION_DENIED) is GhAuthStatus.INVALID_CREDENTIALS

    def test_empty_text_is_invalid(self):
        assert classify_gh_failure_text("") is GhAuthStatus.INVALID_CREDENTIALS


class TestClassifyGhFailureResponse:
    def test_403_with_remaining_budget_is_secondary_limit(self):
        headers = {"x-ratelimit-remaining": "4935", "x-ratelimit-resource": "core"}

        assert (
            classify_gh_failure_response(REST_403_QUOTA, headers)
            is GhAuthStatus.SECONDARY_RATE_LIMITED
        )

    def test_403_with_zero_remaining_is_primary_exhaustion(self):
        headers = {"x-ratelimit-remaining": "0", "x-ratelimit-resource": "core"}

        assert classify_gh_failure_response(REST_403_QUOTA, headers) is GhAuthStatus.RATE_LIMITED

    def test_auth_failure_stays_auth_failure_with_rate_headers(self):
        headers = {"x-ratelimit-remaining": "4935", "x-ratelimit-resource": "core"}

        assert (
            classify_gh_failure_response(PERMISSION_DENIED, headers)
            is GhAuthStatus.INVALID_CREDENTIALS
        )


class TestTransportBlockedClassification:
    """A session-wide GitHub refusal is its own condition, not a bad token.

    Before this classification both bodies fell through to
    INVALID_CREDENTIALS, so every gh-backed script in an agent sandbox told
    the operator to run `gh auth login`. That advice cannot work: the refusal
    is the environment's, and the credential is not what is being refused.
    """

    def test_global_refusal_is_transport_blocked(self):
        """Only the session-wide wording earns the session-wide verdict."""
        assert classify_gh_failure_text(PROXY_REST_403) is GhAuthStatus.TRANSPORT_BLOCKED

    def test_query_scoped_refusal_is_not_transport_blocked(self):
        """A refused GraphQL query is not proof that gh is unusable.

        That body says in the same breath that REST is still served. Because
        this classifier also runs on individual operation failures, treating
        it as a whole-session verdict let one refused query suppress retries
        and declare the transport dead while other gh calls still worked
        (Copilot review on PR #5509).
        """
        assert classify_gh_failure_text(PROXY_GRAPHQL_403) is not GhAuthStatus.TRANSPORT_BLOCKED

    def test_documentation_url_alone_is_not_enough(self):
        """The docs URL rides on both bodies, so it cannot be a global marker."""
        body = (
            "gh: refused (HTTP 403) see "
            "https://docs.anthropic.com/en/docs/claude-code/github-actions"
        )
        assert classify_gh_failure_text(body) is not GhAuthStatus.TRANSPORT_BLOCKED

    def test_a_real_bad_token_is_still_invalid_credentials(self):
        """Negative control: the fallback bucket must keep its own cases."""
        body = "gh: Bad credentials (HTTP 401)"
        assert classify_gh_failure_text(body) is GhAuthStatus.INVALID_CREDENTIALS

    def test_quota_refusal_wins_over_the_session_phrase(self):
        """A throttled session is rate-limited, and that clears on its own."""
        body = (
            "gh: API rate limit exceeded for user ID 6811113 (HTTP 403); "
            "this query is not enabled for this session"
        )
        assert classify_gh_failure_text(body) is GhAuthStatus.RATE_LIMITED

    def test_blocked_wins_over_transient_wording(self):
        """A refusal that mentions a timeout is still permanent for the session."""
        body = "gh: GitHub access is not enabled for this session. (HTTP 403) connection timed out"
        assert classify_gh_failure_text(body) is GhAuthStatus.TRANSPORT_BLOCKED

    def test_a_legitimate_body_reusing_the_phrase_is_not_blocked(self):
        """Negative control the review asked for: the phrase is not the marker.

        A GitHub body that happens to contain the narrower wording must not
        trip the session-wide verdict; only the global phrase does.
        """
        body = "gh: Advanced Security is not enabled for this session's repository (HTTP 403)"
        assert classify_gh_failure_text(body) is not GhAuthStatus.TRANSPORT_BLOCKED

    def test_ordinary_permission_denial_is_untouched(self):
        """Negative control: an integration 403 is not a session refusal."""
        body = "gh: Resource not accessible by integration (HTTP 403)"
        assert classify_gh_failure_text(body) is GhAuthStatus.INVALID_CREDENTIALS

    def test_empty_text_does_not_report_blocked(self):
        assert classify_gh_failure_text("") is not GhAuthStatus.TRANSPORT_BLOCKED
