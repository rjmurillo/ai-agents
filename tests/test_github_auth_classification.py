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
from contextlib import nullcontext
from unittest.mock import patch

import pytest

from scripts.github_core.api import (
    _GRAPHQL_BACKOFF_BASE_SECONDS,
    REFUSAL_BACKOFF_SECONDS,
    GhAuthResult,
    GhAuthStatus,
    _is_retryable_rest_api_error,
    _is_transient_graphql_error,
    assert_gh_authenticated,
    check_gh_auth,
    classify_gh_failure_response,
    classify_gh_failure_text,
    describe_gh_auth_failure,
    gh_graphql,
    is_gh_authenticated,
)
from scripts.github_core.rate_limit import RateLimitStatus, check_workflow_rate_limit

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

# Captured from the binary, not invented: `gh api --hostname
# invalid.example.test --method POST ... --verbose` on gh 2.97.0 emits exactly
# these three lines when it cannot reach the host. None of them carries an HTTP
# status, so before this fix they classified as INVALID_CREDENTIALS and the
# preflight told the operator to run `gh auth login` for a dead network, which
# is the #3139 symptom in its most common form.
GH_DIAL_FAILURE = (
    "dial tcp: lookup invalid.example.test on 127.0.0.53:53: no such host"
)
GH_CONNECT_FAILURE = (
    "error connecting to invalid.example.test\n"
    "check your internet connection or https://githubstatus.com"
)
GH_DNS_FAILURE = "dial tcp: lookup api.github.com: no such host"
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

    def test_rate_limit_text_with_remaining_header_is_secondary(self):
        body = f"{REST_403_QUOTA}\nX-Ratelimit-Remaining: 4935"

        assert classify_gh_failure_text(body) is GhAuthStatus.SECONDARY_RATE_LIMITED

    def test_rest_5xx_is_transient(self):
        assert classify_gh_failure_text(REST_503) is GhAuthStatus.TRANSIENT_ERROR

    @pytest.mark.parametrize(
        "body", [GH_DIAL_FAILURE, GH_CONNECT_FAILURE, GH_DNS_FAILURE]
    )
    def test_gh_connectivity_wording_is_transient(self, body):
        """gh's own transport text carries no HTTP status and no curl wording."""
        assert classify_gh_failure_text(body) is GhAuthStatus.TRANSIENT_ERROR

    def test_bad_credentials_is_invalid(self):
        assert classify_gh_failure_text(BAD_CREDENTIALS) is GhAuthStatus.INVALID_CREDENTIALS

    def test_permission_denial_is_not_a_quota_refusal(self):
        assert (
            classify_gh_failure_text(PERMISSION_DENIED)
            is GhAuthStatus.INVALID_CREDENTIALS
        )

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


class TestGraphqlRetryEnvelope:
    """The retry has to outlast the condition it matches, or it only burns calls.

    Issue #4326 measured the refusal clearing "about a minute" later. The
    original ladder capped the whole retry at 3s and averaged 1.5s, so all three
    attempts landed inside the same refusal window: two extra requests, same
    outcome. These tests measure the envelope, which no classifier assertion can.
    """

    def _run_with_recorded_sleeps(self, bodies, drained, pin_jitter=False):
        calls = [_completed(stderr=body, rc=1) for body in bodies]
        sleeps: list[float] = []
        jitter = patch(
            "random.uniform", side_effect=lambda low, high: high
        ) if pin_jitter else nullcontext()
        with patch("subprocess.run", side_effect=calls), patch(
            "scripts.github_core.api.drained_rate_limit_buckets", return_value=drained
        ), patch("time.sleep", side_effect=sleeps.append), jitter:
            with pytest.raises(RuntimeError) as exc:
                gh_graphql("query { viewer { login } }")
        return sleeps, str(exc.value)

    def test_quota_retry_budget_reaches_the_measured_recovery(self):
        # Pin the jitter to its ceiling so the assertion reads the ladder the
        # code selected. An upper-bound assertion cannot do that: every value
        # the short 1s/2s exponential ladder produces also satisfies
        # `<= 15.0` and `<= 30.0`, so reverting the refusal branch of
        # `_graphql_retry_ceiling` left this test green while the worst-case
        # budget fell from 45s to 3s, back inside the refusal window issue
        # #4326 measured at about a minute.
        sleeps, _ = self._run_with_recorded_sleeps(
            [GRAPHQL_QUOTA] * 3, drained=[], pin_jitter=True
        )

        assert len(sleeps) == 2
        assert sleeps == [REFUSAL_BACKOFF_SECONDS[0], REFUSAL_BACKOFF_SECONDS[1]]
        assert sum(sleeps) >= 45.0

    def test_transient_5xx_keeps_the_short_ladder(self):
        """The long ladder is for refusals only; a 5xx must not wait 45s."""
        sleeps, _ = self._run_with_recorded_sleeps(
            ["HTTP 503 upstream"] * 3, drained=[], pin_jitter=True
        )

        assert len(sleeps) == 2
        assert sum(sleeps) < sum(REFUSAL_BACKOFF_SECONDS)

    def test_drained_bucket_fails_fast_instead_of_burning_attempts(self):
        """Genuine exhaustion resets on the hour; no bounded retry reaches it."""
        sleeps, message = self._run_with_recorded_sleeps(
            [GRAPHQL_QUOTA] * 3, drained=["graphql"]
        )

        assert sleeps == []
        assert "bucket exhausted: graphql" in message

    def test_5xx_keeps_the_short_ladder(self):
        """An upstream wobble clears in seconds; do not sleep a minute on it."""
        sleeps, _ = self._run_with_recorded_sleeps([REST_503] * 3, drained=[])

        assert len(sleeps) == 2
        assert max(sleeps) <= _GRAPHQL_BACKOFF_BASE_SECONDS


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

    @pytest.mark.parametrize(
        "body", [GH_DIAL_FAILURE, GH_CONNECT_FAILURE, GH_DNS_FAILURE]
    )
    def test_lost_connectivity_exits_3_and_never_says_gh_auth_login(
        self, body, capsys
    ):
        calls = [_completed(stderr=body, rc=1), _completed(stderr=body, rc=1)]
        with patch("subprocess.run", side_effect=calls):
            with pytest.raises(SystemExit) as exc:
                assert_gh_authenticated()
        assert exc.value.code == 3
        assert "gh auth login" not in capsys.readouterr().err


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

    def test_healthy_payload_and_served_probes_pass(self):
        # rate_limit payload, REST probe, GraphQL probe.
        calls = [
            _completed(stdout=_HEALTHY_PAYLOAD, rc=0),
            _completed(rc=0),
            _completed(rc=0),
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
            _completed(stdout=_HEALTHY_PAYLOAD, rc=0),
            _completed(rc=0),
            _completed(stderr=GRAPHQL_QUOTA, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            result = check_workflow_rate_limit({"core": 100, "graphql": 50})

        assert result.success is False
        assert result.status == RateLimitStatus.VERIFIED_LIMITED
        assert "GraphQL" in result.probe_error
        assert "REFUSED" in result.summary_markdown

    def test_a_rest_only_caller_does_not_pay_for_a_graphql_probe(self):
        calls = [_completed(stdout=_HEALTHY_PAYLOAD, rc=0), _completed(rc=0)]
        with patch("subprocess.run", side_effect=calls) as run:
            result = check_workflow_rate_limit({"core": 100})

        assert result.success is True
        assert result.status == RateLimitStatus.VERIFIED_HEALTHY
        assert run.call_count == 2

    def test_healthy_payload_with_refused_probe_fails(self):
        calls = [
            _completed(stdout=_HEALTHY_PAYLOAD, rc=0),
            _completed(stderr=RUN_LIST_403_QUOTA, rc=1),
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
        calls = [_completed(stdout=drained, rc=0), _completed(rc=0), _completed(rc=0)]
        with patch("subprocess.run", side_effect=calls):
            result = check_workflow_rate_limit({"core": 100, "graphql": 50})
        assert result.success is False
        assert result.status == RateLimitStatus.VERIFIED_LIMITED
        assert result.probe_error == ""

    @pytest.mark.parametrize("body", [REST_503, GH_CONNECT_FAILURE])
    def test_a_transport_wobble_is_indeterminate_not_success(self, body):
        """The probe reports unknowns without treating them as healthy."""
        calls = [_completed(stdout=_HEALTHY_PAYLOAD, rc=0), _completed(stderr=body, rc=1)]
        with patch("subprocess.run", side_effect=calls):
            result = check_workflow_rate_limit({"core": 100, "graphql": 50})

        assert result.success is False
        assert result.status == RateLimitStatus.COULD_NOT_DETERMINE
        assert result.probe_error != ""
        assert "REFUSED" not in result.summary_markdown
        assert "INDETERMINATE" in result.summary_markdown


# Bodies captured from a Claude Code remote session on 2026-09-03 (gh 2.98.0),
# by running `gh api repos/rjmurillo/ai-agents` and `gh api graphql` against
# the session proxy. Quoted, not synthesized, so these tests cannot encode the
# same assumption the classifier had.
PROXY_REST_403 = (
    '{"message":"GitHub access is not enabled for this session. An org admin '
    'must connect the Claude GitHub App for this organization.",'
    '"documentation_url":"https://docs.anthropic.com/en/docs/claude-code/'
    'github-actions"}\n'
    "gh: GitHub access is not enabled for this session. An org admin must "
    "connect the Claude GitHub App for this organization. (HTTP 403)"
)
PROXY_GRAPHQL_403 = (
    "gh: This GraphQL query is not enabled for this session, only the pinned "
    "set of PR-review operations is served. Use REST via "
    "`gh api repos/{owner}/{repo}/...` instead. (HTTP 403)"
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
        assert (
            classify_gh_failure_text(PROXY_REST_403)
            is GhAuthStatus.TRANSPORT_BLOCKED
        )

    def test_query_scoped_refusal_is_not_transport_blocked(self):
        """A refused GraphQL query is not proof that gh is unusable.

        That body says in the same breath that REST is still served. Because
        this classifier also runs on individual operation failures, treating
        it as a whole-session verdict let one refused query suppress retries
        and declare the transport dead while other gh calls still worked
        (Copilot review on PR #5509).
        """
        assert (
            classify_gh_failure_text(PROXY_GRAPHQL_403)
            is not GhAuthStatus.TRANSPORT_BLOCKED
        )

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
        body = (
            "gh: GitHub access is not enabled for this session. (HTTP 403) "
            "connection timed out"
        )
        assert classify_gh_failure_text(body) is GhAuthStatus.TRANSPORT_BLOCKED

    def test_a_legitimate_body_reusing_the_phrase_is_not_blocked(self):
        """Negative control the review asked for: the phrase is not the marker.

        A GitHub body that happens to contain the narrower wording must not
        trip the session-wide verdict; only the global phrase does.
        """
        body = (
            "gh: Advanced Security is not enabled for this session's "
            "repository (HTTP 403)"
        )
        assert classify_gh_failure_text(body) is not GhAuthStatus.TRANSPORT_BLOCKED

    def test_ordinary_permission_denial_is_untouched(self):
        """Negative control: an integration 403 is not a session refusal."""
        body = "gh: Resource not accessible by integration (HTTP 403)"
        assert classify_gh_failure_text(body) is GhAuthStatus.INVALID_CREDENTIALS

    def test_empty_text_does_not_report_blocked(self):
        assert classify_gh_failure_text("") is not GhAuthStatus.TRANSPORT_BLOCKED


class TestTransportBlockedRemedy:
    """The message an agent reads decides its next call, so it must be true."""

    def _describe(self):
        return describe_gh_auth_failure(
            GhAuthResult(GhAuthStatus.TRANSPORT_BLOCKED, "HTTP 403")
        )

    def test_exit_code_is_config_not_external(self):
        """Exit 3 advertises 'retryable', and a refused session never clears."""
        _, code, error_type = self._describe()
        assert code == 2
        assert error_type == "ApiError"

    def test_message_does_not_send_the_operator_to_gh_auth_login(self):
        message, _, _ = self._describe()
        assert "gh auth login" in message
        # Present only as the remedy being ruled out, never as the instruction.
        assert "Run 'gh auth login' first" not in message

    def test_message_names_the_transport_that_works(self):
        message, _, _ = self._describe()
        assert "mcp__github__" in message

    def test_detail_is_appended_for_diagnosis(self):
        message, _, _ = self._describe()
        assert "HTTP 403" in message

    def test_a_bad_token_keeps_the_auth_remedy(self):
        """Negative control: the auth path is unchanged."""
        message, code, error_type = describe_gh_auth_failure(
            GhAuthResult(GhAuthStatus.INVALID_CREDENTIALS)
        )
        assert code == 4
        assert error_type == "AuthError"
        assert "gh auth login" in message


class TestTransportBlockedIsNotRetried:
    """Retrying a refused session burns the run's budget for no chance of success."""

    @pytest.mark.parametrize("body", [PROXY_REST_403, PROXY_GRAPHQL_403])
    def test_rest_retry_ladder_declines(self, body):
        assert _is_retryable_rest_api_error(body) is False

    @pytest.mark.parametrize("body", [PROXY_REST_403, PROXY_GRAPHQL_403])
    def test_graphql_retry_ladder_declines(self, body):
        assert _is_transient_graphql_error(body) is False

    def test_a_5xx_is_still_retried(self):
        """Negative control: the retry ladder still fires for real transients."""
        assert _is_transient_graphql_error("HTTP 503 Service Unavailable") is True


class TestBothTransportsProveASessionRefusal:
    """A session-wide verdict needs both transports refused, not one body.

    ``check_gh_auth`` is the only caller that observes REST and GraphQL
    together, so it is the only place a narrower refusal is promoted.
    """

    def test_rest_and_graphql_both_refused_is_transport_blocked(self):
        calls = [
            _completed(stderr="gh: not enabled for this session", rc=1),
            _completed(stderr=PROXY_GRAPHQL_403, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.TRANSPORT_BLOCKED

    def test_graphql_success_after_rest_refusal_is_authenticated(self):
        """Negative control: one transport working is not a blocked session."""
        calls = [
            _completed(stderr="gh: not enabled for this session", rc=1),
            _completed(stdout='{"data":{"viewer":{"login":"x"}}}', rc=0),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.AUTHENTICATED

    def test_a_transient_rest_failure_is_not_promoted(self):
        """The mixed-failure case: 503 plus a query-scoped refusal.

        Both probes fail, but neither proves the session is refused: REST may
        recover, and the GraphQL body scopes itself to one query. Promoting
        this suppressed the REST retry ladder for a condition that clears
        (Copilot review on PR #5509).
        """
        calls = [
            _completed(stderr="HTTP 503: Service unavailable", rc=1),
            _completed(stderr=PROXY_GRAPHQL_403, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is not GhAuthStatus.TRANSPORT_BLOCKED

    def test_rest_global_refusal_alone_is_enough(self):
        """The account-level denial closes the session whatever GraphQL says."""
        calls = [
            _completed(stderr=PROXY_REST_403, rc=1),
            _completed(stderr="HTTP 503: Service unavailable", rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.TRANSPORT_BLOCKED

    def test_a_plain_bad_token_on_both_is_still_invalid_credentials(self):
        """Negative control: no policy wording, so no promotion."""
        calls = [
            _completed(stderr="gh: Bad credentials", rc=1),
            _completed(stderr="gh: Bad credentials (HTTP 401)", rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.INVALID_CREDENTIALS
