"""Transport and quota classification for the gh auth preflight.

Covers issues #3139 (a REST 5xx read as invalid credentials), #4344 (an
exhausted GraphQL quota read as missing gh), and #4326 (a 403 quota refusal
classified permanent and a pre-flight gate blind to it).

Every rate-limit fixture below is a body captured from GitHub and quoted in the
issue threads, not a synthesized one, so the tests cannot encode the same
assumption the code had.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from scripts.github_core.api import (
    GhAuthStatus,
    _is_transient_graphql_error,
    assert_gh_authenticated,
    check_gh_auth,
    classify_gh_failure_text,
    is_gh_authenticated,
)
from scripts.github_core.rate_limit import check_workflow_rate_limit

# Captured refusal bodies (issue #4326 Observations A, B, and the third
# observation; issue #4335 workflow log).
REST_403_QUOTA = "gh: API rate limit exceeded for user ID 6811113 (HTTP 403)"
RUN_LIST_403_QUOTA = (
    "failed to get runs: HTTP 403: API rate limit exceeded for user ID 6811113"
)
REST_BODY_QUOTA = (
    '{"message": "API rate limit exceeded for user ID 6811113", '
    '"documentation_url": "https://docs.github.com/rest/overview/'
    'resources-in-the-rest-api#rate-limiting"}'
)
GRAPHQL_QUOTA = "GraphQL: API rate limit already exceeded for user ID 6811113."
SECONDARY_LIMIT = (
    "You have exceeded a secondary rate limit and have been temporarily blocked "
    "from content creation. Please retry your request again later."
)

# Captured from issue #3139: authenticated REST returned the GitHub Unicorn page.
REST_503 = "HTTP 503: Service unavailable (https://api.github.com/user)"
# A genuine permission denial. Also 403, and must stay permanent.
PERMISSION_DENIED = "HTTP 403: Resource not accessible by integration"
BAD_CREDENTIALS = "HTTP 401: Bad credentials (https://api.github.com/user)"


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(
        args=["gh"], returncode=rc, stdout=stdout, stderr=stderr
    )


class TestClassifyGhFailureText:
    @pytest.mark.parametrize(
        "body",
        [REST_403_QUOTA, RUN_LIST_403_QUOTA, REST_BODY_QUOTA, GRAPHQL_QUOTA],
    )
    def test_primary_quota_refusal_is_rate_limited(self, body):
        assert classify_gh_failure_text(body) is GhAuthStatus.RATE_LIMITED

    def test_secondary_limit_is_its_own_status(self):
        assert (
            classify_gh_failure_text(SECONDARY_LIMIT)
            is GhAuthStatus.SECONDARY_RATE_LIMITED
        )

    def test_rest_5xx_is_transient(self):
        assert classify_gh_failure_text(REST_503) is GhAuthStatus.TRANSIENT_ERROR

    def test_bad_credentials_is_invalid(self):
        assert classify_gh_failure_text(BAD_CREDENTIALS) is GhAuthStatus.INVALID_CREDENTIALS

    def test_permission_denial_is_not_a_quota_refusal(self):
        assert (
            classify_gh_failure_text(PERMISSION_DENIED)
            is GhAuthStatus.INVALID_CREDENTIALS
        )

    def test_empty_text_is_invalid(self):
        assert classify_gh_failure_text("") is GhAuthStatus.INVALID_CREDENTIALS


class TestIsTransientGraphqlError:
    @pytest.mark.parametrize(
        "body", [REST_403_QUOTA, RUN_LIST_403_QUOTA, GRAPHQL_QUOTA, SECONDARY_LIMIT]
    )
    def test_quota_refusal_is_retried(self, body):
        assert _is_transient_graphql_error(body) is True

    @pytest.mark.parametrize("body", ["gh: something (HTTP 429)", "HTTP 503 upstream"])
    def test_existing_transient_statuses_still_retry(self, body):
        assert _is_transient_graphql_error(body) is True

    @pytest.mark.parametrize("body", [PERMISSION_DENIED, BAD_CREDENTIALS, "HTTP 404"])
    def test_permanent_failures_are_not_retried(self, body):
        assert _is_transient_graphql_error(body) is False


class TestCheckGhAuth:
    def test_authenticated_when_auth_status_succeeds(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assert check_gh_auth().status is GhAuthStatus.AUTHENTICATED

    def test_rest_503_with_working_graphql_is_authenticated(self):
        # Issue #3139: gh auth status fails on a REST 503 while the same token
        # still authenticates GraphQL.
        calls = [
            _completed(stderr=REST_503, rc=1),
            _completed(stdout='{"data":{"viewer":{"login":"rjmurillo"}}}', rc=0),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.AUTHENTICATED

    def test_rest_503_with_failing_graphql_is_transient(self):
        calls = [
            _completed(stderr=REST_503, rc=1),
            _completed(stderr=REST_503, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.TRANSIENT_ERROR

    def test_exhausted_graphql_quota_is_rate_limited(self):
        # Issue #4344: both gate scripts reported missing gh in this state.
        calls = [
            _completed(stderr=REST_403_QUOTA, rc=1),
            _completed(stderr=GRAPHQL_QUOTA, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.RATE_LIMITED

    def test_secondary_throttle_keeps_its_own_status(self):
        calls = [
            _completed(stderr=SECONDARY_LIMIT, rc=1),
            _completed(stderr=SECONDARY_LIMIT, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.SECONDARY_RATE_LIMITED

    def test_missing_gh_binary(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert check_gh_auth().status is GhAuthStatus.MISSING_GH

    def test_confirmed_bad_credentials(self):
        calls = [
            _completed(stderr=BAD_CREDENTIALS, rc=1),
            _completed(stderr=BAD_CREDENTIALS, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.INVALID_CREDENTIALS

    def test_detail_redacts_a_token(self):
        leaked = "bad credentials for ghp_" + "A" * 36
        calls = [_completed(stderr=leaked, rc=1), _completed(stderr=leaked, rc=1)]
        with patch("subprocess.run", side_effect=calls):
            detail = check_gh_auth().detail
        assert "ghp_" not in detail
        assert "[REDACTED]" in detail

    def test_is_gh_authenticated_wrapper_tracks_the_classification(self):
        calls = [
            _completed(stderr=REST_503, rc=1),
            _completed(stdout='{"data":{"viewer":{"login":"x"}}}', rc=0),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert is_gh_authenticated() is True


class TestAssertGhAuthenticatedExitCodes:
    def test_success_does_not_exit(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assert assert_gh_authenticated() is None

    @pytest.mark.parametrize("body", [REST_503, REST_403_QUOTA, SECONDARY_LIMIT])
    def test_upstream_conditions_exit_3(self, body, capsys):
        # Three gh calls: auth status, graphql probe, and the best-effort
        # rate_limit lookup that enriches a quota diagnostic.
        calls = [
            _completed(stderr=body, rc=1),
            _completed(stderr=body, rc=1),
            _completed(stdout="{}", rc=0),
        ]
        with patch("subprocess.run", side_effect=calls):
            with pytest.raises(SystemExit) as exc:
                assert_gh_authenticated()
        assert exc.value.code == 3
        assert "gh auth login" not in capsys.readouterr().err

    def test_quota_message_names_the_bucket_and_reset(self, capsys):
        payload = json.dumps(
            {
                "resources": {
                    "core": {"remaining": 4834, "limit": 5000, "reset": 1750000000},
                    "graphql": {"remaining": 0, "limit": 5000, "reset": 1750000000},
                }
            }
        )
        calls = [
            _completed(stderr=REST_403_QUOTA, rc=1),
            _completed(stderr=GRAPHQL_QUOTA, rc=1),
            _completed(stdout=payload, rc=0),
        ]
        with patch("subprocess.run", side_effect=calls):
            with pytest.raises(SystemExit):
                assert_gh_authenticated()
        err = capsys.readouterr().err
        assert "graphql 0/5000" in err
        assert "2025-06-15" in err

    def test_missing_gh_exits_4(self, capsys):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(SystemExit) as exc:
                assert_gh_authenticated()
        assert exc.value.code == 4
        assert "gh auth login" in capsys.readouterr().err

    def test_bad_credentials_exits_4(self, capsys):
        calls = [
            _completed(stderr=BAD_CREDENTIALS, rc=1),
            _completed(stderr=BAD_CREDENTIALS, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            with pytest.raises(SystemExit) as exc:
                assert_gh_authenticated()
        assert exc.value.code == 4
        assert "gh auth login" in capsys.readouterr().err


_HEALTHY_PAYLOAD = json.dumps(
    {
        "resources": {
            "core": {"remaining": 4984, "limit": 5000, "reset": 1750000000},
            "graphql": {"remaining": 1694, "limit": 5000, "reset": 1750000000},
        }
    }
)


class TestRateLimitGateProbe:
    """Issue #4326 defect 2: healthy quota numbers during a live refusal."""

    def test_healthy_payload_and_served_probe_passes(self):
        calls = [_completed(stdout=_HEALTHY_PAYLOAD, rc=0), _completed(rc=0)]
        with patch("subprocess.run", side_effect=calls):
            result = check_workflow_rate_limit({"core": 100, "graphql": 50})
        assert result.success is True
        assert result.probe_error == ""

    def test_healthy_payload_with_refused_probe_fails(self):
        calls = [
            _completed(stdout=_HEALTHY_PAYLOAD, rc=0),
            _completed(stderr=RUN_LIST_403_QUOTA, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            result = check_workflow_rate_limit({"core": 100, "graphql": 50})
        assert result.success is False
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
        calls = [_completed(stdout=drained, rc=0), _completed(rc=0)]
        with patch("subprocess.run", side_effect=calls):
            result = check_workflow_rate_limit({"core": 100, "graphql": 50})
        assert result.success is False
        assert result.probe_error == ""
