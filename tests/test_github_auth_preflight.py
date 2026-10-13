"""Gh auth preflight and the rate-limit gate probe (issues #3139, #4326).

Captured refusal bodies live in ``tests/gh_auth_refusal_fixtures.py``.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from scripts.github_core.api import (
    GhAuthStatus,
    check_gh_auth,
    is_gh_authenticated,
)
from scripts.github_core.rate_limit import RateLimitStatus, check_workflow_rate_limit
from tests.gh_auth_refusal_fixtures import (
    BAD_CREDENTIALS,
    GH_CONNECT_FAILURE,
    GRAPHQL_QUOTA,
    REST_403_QUOTA,
    REST_503,
    RUN_LIST_403_QUOTA,
    SECONDARY_LIMIT,
    completed,
)

_HEALTHY_PAYLOAD = json.dumps(
    {
        "resources": {
            "core": {"remaining": 4984, "limit": 5000, "reset": 1750000000},
            "graphql": {"remaining": 1694, "limit": 5000, "reset": 1750000000},
        }
    }
)


class TestCheckGhAuth:
    def test_authenticated_when_auth_status_succeeds(self):
        with patch("subprocess.run", return_value=completed(rc=0)):
            assert check_gh_auth().status is GhAuthStatus.AUTHENTICATED

    def test_rest_503_with_working_graphql_is_authenticated(self):
        # Issue #3139: gh auth status fails on a REST 503 while the same token
        # still authenticates GraphQL.
        calls = [
            completed(stderr=REST_503, rc=1),
            completed(stdout='{"data":{"viewer":{"login":"rjmurillo"}}}', rc=0),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.AUTHENTICATED

    def test_rest_503_with_failing_graphql_is_transient(self):
        calls = [
            completed(stderr=REST_503, rc=1),
            completed(stderr=REST_503, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.TRANSIENT_ERROR

    def test_exhausted_graphql_quota_is_rate_limited(self):
        # Issue #4344: both gate scripts reported missing gh in this state.
        calls = [
            completed(stderr=REST_403_QUOTA, rc=1),
            completed(stderr=GRAPHQL_QUOTA, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.RATE_LIMITED

    def test_secondary_throttle_keeps_its_own_status(self):
        calls = [
            completed(stderr=SECONDARY_LIMIT, rc=1),
            completed(stderr=SECONDARY_LIMIT, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.SECONDARY_RATE_LIMITED

    def test_missing_gh_binary(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert check_gh_auth().status is GhAuthStatus.MISSING_GH

    def test_confirmed_bad_credentials(self):
        calls = [
            completed(stderr=BAD_CREDENTIALS, rc=1),
            completed(stderr=BAD_CREDENTIALS, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.INVALID_CREDENTIALS

    def test_detail_redacts_a_token(self):
        leaked = "bad credentials for ghp_" + "A" * 36
        calls = [completed(stderr=leaked, rc=1), completed(stderr=leaked, rc=1)]
        with patch("subprocess.run", side_effect=calls):
            detail = check_gh_auth().detail
        assert "ghp_" not in detail
        assert "[REDACTED]" in detail

    def test_is_gh_authenticated_wrapper_tracks_the_classification(self):
        calls = [
            completed(stderr=REST_503, rc=1),
            completed(stdout='{"data":{"viewer":{"login":"x"}}}', rc=0),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert is_gh_authenticated() is True


class TestRateLimitGateProbe:
    """Issue #4326 defect 2: healthy quota numbers during a live refusal."""

    def test_healthy_payload_and_served_probes_pass(self):
        # rate_limit payload, REST probe, GraphQL probe.
        calls = [
            completed(stdout=_HEALTHY_PAYLOAD, rc=0),
            completed(rc=0),
            completed(rc=0),
        ]
        with patch("subprocess.run", side_effect=calls):
            result = check_workflow_rate_limit({"core": 100, "graphql": 50})
        assert result.success is True
        assert result.status == RateLimitStatus.VERIFIED_HEALTHY
        assert result.probe_error == ""

    def test_graphql_only_refusal_closes_the_gate(self):
        """REST and GraphQL refuse independently (issue #4326 defect 2).

        A core-only probe reports the API healthy right through the
        GraphQL-only window that issues #4344, #4333, and #4335 were all filed
        from, because `gh api meta` keeps answering.
        """
        calls = [
            completed(stdout=_HEALTHY_PAYLOAD, rc=0),
            completed(rc=0),
            completed(stderr=GRAPHQL_QUOTA, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            result = check_workflow_rate_limit({"core": 100, "graphql": 50})

        assert result.success is False
        assert result.status == RateLimitStatus.VERIFIED_LIMITED
        assert "GraphQL" in result.probe_error
        assert "REFUSED" in result.summary_markdown

    def test_a_rest_only_caller_does_not_pay_for_a_graphql_probe(self):
        calls = [completed(stdout=_HEALTHY_PAYLOAD, rc=0), completed(rc=0)]
        with patch("subprocess.run", side_effect=calls) as run:
            result = check_workflow_rate_limit({"core": 100})

        assert result.success is True
        assert result.status == RateLimitStatus.VERIFIED_HEALTHY
        assert run.call_count == 2

    def test_healthy_payload_with_refused_probe_fails(self):
        calls = [
            completed(stdout=_HEALTHY_PAYLOAD, rc=0),
            completed(stderr=RUN_LIST_403_QUOTA, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            result = check_workflow_rate_limit({"core": 100, "graphql": 50})
        assert result.success is False
        assert result.status == RateLimitStatus.VERIFIED_LIMITED
        assert "API rate limit exceeded" in result.probe_error
        assert "REFUSED" in result.summary_markdown

    def test_exhausted_threshold_still_fails_when_probe_is_served(self):
        drained = json.dumps(
            {
                "resources": {
                    "core": {"remaining": 4950, "limit": 5000, "reset": 1750000000},
                    "graphql": {"remaining": 0, "limit": 5000, "reset": 1750000000},
                }
            }
        )
        calls = [completed(stdout=drained, rc=0), completed(rc=0), completed(rc=0)]
        with patch("subprocess.run", side_effect=calls):
            result = check_workflow_rate_limit({"core": 100, "graphql": 50})
        assert result.success is False
        assert result.status == RateLimitStatus.VERIFIED_LIMITED
        assert result.probe_error == ""

    @pytest.mark.parametrize("body", [REST_503, GH_CONNECT_FAILURE])
    def test_a_transport_wobble_is_indeterminate_not_success(self, body):
        """The probe reports unknowns without treating them as healthy."""
        calls = [completed(stdout=_HEALTHY_PAYLOAD, rc=0), completed(stderr=body, rc=1)]
        with patch("subprocess.run", side_effect=calls):
            result = check_workflow_rate_limit({"core": 100, "graphql": 50})

        assert result.success is False
        assert result.status == RateLimitStatus.COULD_NOT_DETERMINE
        assert result.probe_error != ""
        assert "REFUSED" not in result.summary_markdown
        assert "INDETERMINATE" in result.summary_markdown
