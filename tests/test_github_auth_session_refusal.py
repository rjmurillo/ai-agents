"""Both transports must refuse before a session-wide verdict (PR #5509).

Captured refusal bodies live in ``tests/gh_auth_refusal_fixtures.py``.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from scripts.github_core.api import (
    GhAuthResult,
    GhAuthStatus,
    assert_gh_authenticated,
    check_gh_auth,
    describe_gh_auth_failure,
)
from tests.gh_auth_refusal_fixtures import (
    BAD_CREDENTIALS,
    GH_AUTH_STATUS_INVALID,
    PROXY_GRAPHQL_403,
    PROXY_REST_403,
    REST_403_QUOTA,
    completed,
)


class TestBothTransportsProveASessionRefusal:
    """A session-wide verdict needs both transports refused, not one body.

    ``check_gh_auth`` is the only caller that observes REST and GraphQL
    together, so it is the only place a narrower refusal is promoted.
    """

    def test_rest_and_graphql_both_refused_is_transport_blocked(self):
        calls = [
            completed(stderr="gh: not enabled for this session", rc=1),
            completed(stderr=PROXY_GRAPHQL_403, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.TRANSPORT_BLOCKED

    def test_graphql_success_after_rest_refusal_is_authenticated(self):
        """Negative control: one transport working is not a blocked session."""
        calls = [
            completed(stderr="gh: not enabled for this session", rc=1),
            completed(stdout='{"data":{"viewer":{"login":"x"}}}', rc=0),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.AUTHENTICATED

    def test_a_transient_rest_failure_keeps_its_retryable_verdict(self):
        """The mixed-failure case: 503 plus a query-scoped refusal.

        Both probes fail, but neither proves the session is refused: REST may
        recover, and the GraphQL body scopes itself to one query. Promoting
        this suppressed the REST retry ladder for a condition that clears
        (Copilot review on PR #5509).

        Asserting only "not TRANSPORT_BLOCKED" passed while the pair returned
        INVALID_CREDENTIALS at exit 4, which is the same wrong remedy the whole
        status exists to stop: `gh auth login` for a token nothing measured.
        The GraphQL refusal carries no credential evidence, so the verdict has
        to be the one REST actually reported.
        """
        calls = [
            completed(stderr="HTTP 503: Service unavailable", rc=1),
            completed(stderr=PROXY_GRAPHQL_403, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            result = check_gh_auth()
        assert result.status is GhAuthStatus.TRANSIENT_ERROR
        _, exit_code, _ = describe_gh_auth_failure(result)
        assert exit_code == 3

    def test_gh_auth_status_calling_the_token_invalid_is_not_evidence(self):
        """The live shape on 2026-09-03, and the one that still exited 4.

        `gh auth status` renders any failure of its own call as "The token in
        GH_TOKEN is invalid", so a proxy refusing one endpoint by policy reads
        as a bad token. Measured in the same session: `gh api user` returned
        the real account while `gh auth status` said the token was invalid and
        both `gh api repos/{owner}/{repo}` and GraphQL were refused 403.

        With GraphQL refused by policy, the confirmation check_gh_auth exists
        to make did not happen, so the REST probe is the only decisive question
        left. A credential that authenticates means the refusal is the session
        policy, which is exit 2 and the MCP transport, not exit 4 and
        `gh auth login`.
        """
        calls = [
            completed(stderr=GH_AUTH_STATUS_INVALID, rc=1),
            completed(stderr=PROXY_GRAPHQL_403, rc=1),
            completed(stdout='{"login": "rjmurillo"}', rc=0),
            completed(stderr=PROXY_REST_403, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            result = check_gh_auth()
        assert result.status is GhAuthStatus.TRANSPORT_BLOCKED
        _, exit_code, _ = describe_gh_auth_failure(result)
        assert exit_code == 2

    def test_a_credential_that_fails_the_rest_probe_is_still_invalid(self):
        """The negative control for the case above, same first two calls.

        The two cases differ only in what `gh api user` returns, which is the
        whole point: without this one the REST confirmation could return
        TRANSPORT_BLOCKED unconditionally and no test would fail. A real 401
        there has to keep exit 4, or a genuinely expired token is routed to a
        transport that cannot fix it either.
        """
        calls = [
            completed(stderr=GH_AUTH_STATUS_INVALID, rc=1),
            completed(stderr=PROXY_GRAPHQL_403, rc=1),
            completed(stderr=BAD_CREDENTIALS, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            result = check_gh_auth()
        assert result.status is GhAuthStatus.INVALID_CREDENTIALS
        _, exit_code, _ = describe_gh_auth_failure(result)
        assert exit_code == 4

    def test_a_rest_timeout_does_not_skip_the_credential_confirmation(self):
        """The timeout branch used to return the GraphQL probe directly.

        That early return sat above every recovery below it, so a `gh auth
        status` timeout paired with a query-scoped policy refusal exited 4 and
        recommended `gh auth login` having measured nothing at all: REST said
        nothing, and GraphQL answered about the policy. A timeout is the case
        with the least credential evidence of any, so it is the last one that
        should reach the credential verdict.
        """
        calls = [
            subprocess.TimeoutExpired(cmd="gh", timeout=10),
            completed(stderr=PROXY_GRAPHQL_403, rc=1),
            completed(stdout='{"login": "rjmurillo"}', rc=0),
            completed(stderr=PROXY_REST_403, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            result = check_gh_auth()
        assert result.status is GhAuthStatus.TRANSPORT_BLOCKED
        _, exit_code, _ = describe_gh_auth_failure(result)
        assert exit_code == 2

    def test_a_rest_timeout_with_a_genuinely_bad_token_still_exits_4(self):
        """Control for the case above: the timeout must not launder a bad token.

        Same first two calls, so only the REST probe's answer separates them.
        Without this, the timeout branch could return TRANSPORT_BLOCKED
        unconditionally and no test would fail.
        """
        calls = [
            subprocess.TimeoutExpired(cmd="gh", timeout=10),
            completed(stderr=PROXY_GRAPHQL_403, rc=1),
            completed(stderr=BAD_CREDENTIALS, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            result = check_gh_auth()
        assert result.status is GhAuthStatus.INVALID_CREDENTIALS
        _, exit_code, _ = describe_gh_auth_failure(result)
        assert exit_code == 4

    def test_a_rest_timeout_is_never_evidence_of_a_session_refusal(self):
        """An empty REST body must not satisfy the both-transports test.

        The timeout leaves `rest_text` empty, and the session-wide verdict
        needs a policy refusal on both transports. If the empty string ever
        matched, every timeout beside a scoped refusal would read as a refused
        session without the credential probe running at all.
        """
        calls = [
            subprocess.TimeoutExpired(cmd="gh", timeout=10),
            completed(stderr=BAD_CREDENTIALS, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls) as run:
            result = check_gh_auth()
        assert result.status is GhAuthStatus.INVALID_CREDENTIALS
        assert run.call_count == 2

    def test_a_graphql_credential_failure_never_reaches_the_rest_probe(self):
        """GraphQL answered the credential question, so nothing needs confirming.

        Pinning the call count is what keeps the probe on its narrow path: a
        third gh invocation on every auth check would cost one round trip per
        call site for a case that is already decided.
        """
        calls = [
            completed(stderr=GH_AUTH_STATUS_INVALID, rc=1),
            completed(stderr=BAD_CREDENTIALS, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls) as run:
            result = check_gh_auth()
        assert result.status is GhAuthStatus.INVALID_CREDENTIALS
        assert run.call_count == 2

    def test_rest_global_refusal_alone_is_enough(self):
        """Ordering only: the denial signature outranks a GraphQL wobble.

        The body is not one `gh auth status` emits, so this pins the branch's
        precedence rather than a reachable path. The reachable form of this
        case is a repository call, which this function never makes; the
        preflight's capability probe covers it (Copilot review on PR #5509).
        """
        calls = [
            completed(stderr=PROXY_REST_403, rc=1),
            completed(stderr="HTTP 503: Service unavailable", rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.TRANSPORT_BLOCKED

    def test_an_account_level_denial_survives_a_successful_graphql_probe(self):
        """Ordering only, for the same reason as the case above.

        A viewer query is not repository-scoped, so its success proves less
        than it looks. This case pins that the denial signature is read before
        the success return, which is correct precedence. What it does not do,
        despite an earlier docstring here claiming it, is protect the real
        mixed session: `gh auth status` emits its own invalid-token text there,
        not this body, so the branch never fires and this function returns
        AUTHENTICATED. That gap is pinned directly below and closed by the
        preflight (Copilot review on PR #5509).
        """
        calls = [
            completed(stderr=PROXY_REST_403, rc=1),
            completed(stdout='{"data": {"viewer": {"login": "x"}}}', rc=0),
        ]
        with patch("subprocess.run", side_effect=calls):
            result = check_gh_auth()
        assert result.status is GhAuthStatus.TRANSPORT_BLOCKED
        _, exit_code, _ = describe_gh_auth_failure(result)
        assert exit_code == 2

    def test_a_repository_denial_is_invisible_to_this_function(self):
        """The gap, stated rather than implied.

        Every subprocess response here is from the command that produces it:
        `gh auth status` reporting the token invalid, then a served viewer
        query. That is the session shape measured on 2026-09-03 with the
        repository REST endpoint also denied, and this function returns
        AUTHENTICATED because it never asks a repository anything.

        This is not a defect to fix here. `check_gh_auth` answers "does any
        transport authenticate", which is the deliberate #3139 contract shared
        by eight callers, and widening it to a repository probe would add a
        network call to all of them. The question "can this workflow run" is
        the preflight's, and `check_github_transport` now probes for it.
        Asserting the limitation keeps it from being rediscovered as a
        surprise (Copilot review on PR #5509).
        """
        calls = [
            completed(stderr=GH_AUTH_STATUS_INVALID, rc=1),
            completed(stdout='{"data": {"viewer": {"login": "x"}}}', rc=0),
        ]
        with patch("subprocess.run", side_effect=calls):
            result = check_gh_auth()
        assert result.status is GhAuthStatus.AUTHENTICATED

    def test_a_transient_rest_failure_beside_a_working_probe_is_still_authenticated(
        self,
    ):
        """Control: the short-circuit must read the denial, not any REST failure.

        This is the #3139 fix itself. A REST 5xx beside a working GraphQL token
        has to stay AUTHENTICATED, or the guard above would relabel every
        transient outage as a refused session and send the whole repository to
        MCP for a condition that clears by itself.
        """
        calls = [
            completed(stderr="HTTP 503: Service unavailable", rc=1),
            completed(stdout='{"data": {"viewer": {"login": "x"}}}', rc=0),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().is_authenticated

    def test_a_quota_probe_still_outranks_the_account_level_denial(self):
        """Control: ordering, not just presence.

        Quota has a reset and the denial does not, so a throttled session must
        not be relabelled as refused. The denial check sits after the quota
        check for exactly this pair; swapping them returns exit 2 for something
        that clears in a minute.
        """
        calls = [
            completed(stderr=PROXY_REST_403, rc=1),
            completed(stderr=REST_403_QUOTA, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            result = check_gh_auth()
        assert result.status is GhAuthStatus.RATE_LIMITED
        _, exit_code, _ = describe_gh_auth_failure(result)
        assert exit_code == 3

    def test_an_account_level_denial_outranks_a_confirmed_bad_token(self):
        """Both faults are real; only one of them has a remedy that works.

        REST returns the org-level denial and GraphQL returns a genuine 401, so
        the token is bad AND the session is refused. Reporting
        INVALID_CREDENTIALS sends the operator to `gh auth login`, after which
        every gh call still returns 403, which is the loop issues #3139 and
        #4344 record. The denial dominates because no credential action clears
        it, and the caller has a transport that does work.

        This is a deliberate change from the pre-existing behavior for this
        pair, which returned INVALID_CREDENTIALS. It is pinned here so the
        choice is visible rather than incidental, and the message is worded to
        say repairing the credential cannot clear this, never that the
        credential is sound (Copilot review on PR #5509).
        """
        calls = [
            completed(stderr=PROXY_REST_403, rc=1),
            completed(stderr=BAD_CREDENTIALS, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            result = check_gh_auth()
        assert result.status is GhAuthStatus.TRANSPORT_BLOCKED
        message, exit_code, _ = describe_gh_auth_failure(result)
        assert exit_code == 2
        assert "credential is not the fault" not in message
        assert "Repairing the credential cannot clear it" in message

    def test_a_bad_token_without_a_session_denial_is_still_a_credential_fault(self):
        """Control: only the account-level wording outranks the 401.

        Same GraphQL 401, REST wording the classifier does not recognize as a
        denial. Without this the promotion could widen to "any REST failure
        beside a 401 is a blocked session" and route a fixable token away from
        the one remedy that fixes it.
        """
        calls = [
            completed(stderr="gh: could not determine status", rc=1),
            completed(stderr=BAD_CREDENTIALS, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            result = check_gh_auth()
        assert result.status is GhAuthStatus.INVALID_CREDENTIALS
        _, exit_code, _ = describe_gh_auth_failure(result)
        assert exit_code == 4

    def test_a_graphql_quota_survives_a_rest_session_refusal(self):
        """Quota outranks promotion: it has a reset, TRANSPORT_BLOCKED does not.

        Overwriting it would convert a condition that clears into a config
        failure and drop the retry the caller should make (Copilot review on
        PR #5509).
        """
        calls = [
            completed(stderr=PROXY_REST_403, rc=1),
            completed(stderr=REST_403_QUOTA, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.RATE_LIMITED

    def test_a_plain_bad_token_on_both_is_still_invalid_credentials(self):
        """Negative control: no policy wording, so no promotion."""
        calls = [
            completed(stderr="gh: Bad credentials", rc=1),
            completed(stderr="gh: Bad credentials (HTTP 401)", rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            assert check_gh_auth().status is GhAuthStatus.INVALID_CREDENTIALS


class TestGraphqlOnlyRefusal:
    """A valid credential, refused GraphQL, and served repository REST (issue #5693).

    ``gh api user`` is account-scoped, so only a repository call can separate
    a GraphQL-only refusal from a session that refuses repository REST too.
    The first three calls are the live shape measured on 2026-09-03; the
    fourth is the repository probe and is the only thing that differs.
    """

    @staticmethod
    def _until_user_probe() -> list:
        return [
            completed(stderr=GH_AUTH_STATUS_INVALID, rc=1),
            completed(stderr=PROXY_GRAPHQL_403, rc=1),
            completed(stdout='{"login": "rjmurillo"}', rc=0),
        ]

    def test_repository_rest_served_is_graphql_blocked(self):
        calls = [*self._until_user_probe(), completed(stdout='{"name": "ai-agents"}', rc=0)]
        with patch("subprocess.run", side_effect=calls) as run:
            result = check_gh_auth()
        assert result.status is GhAuthStatus.GRAPHQL_BLOCKED
        assert run.call_args_list[-1].args[0] == ["gh", "api", "repos/{owner}/{repo}"]

    def test_graphql_blocked_has_its_own_message_and_exit_2(self):
        calls = [*self._until_user_probe(), completed(stdout="{}", rc=0)]
        with patch("subprocess.run", side_effect=calls):
            result = check_gh_auth()
        message, exit_code, error_type = describe_gh_auth_failure(result)
        assert exit_code == 2
        assert error_type == "ApiError"
        assert "Use REST" in message
        assert "regardless of the token" not in message

    def test_repository_rest_refused_stays_transport_blocked(self):
        """Negative control: only the repository probe separates the two."""
        calls = [*self._until_user_probe(), completed(stderr=PROXY_REST_403, rc=1)]
        with patch("subprocess.run", side_effect=calls):
            result = check_gh_auth()
        assert result.status is GhAuthStatus.TRANSPORT_BLOCKED

    def test_repository_probe_timeout_stays_transport_blocked(self):
        """A probe that never answered is not evidence that REST works."""
        calls = [*self._until_user_probe(), subprocess.TimeoutExpired(cmd="gh", timeout=10)]
        with patch("subprocess.run", side_effect=calls):
            result = check_gh_auth()
        assert result.status is GhAuthStatus.TRANSPORT_BLOCKED

    def test_a_failed_credential_probe_never_reaches_the_repository_probe(self):
        """A bad token must keep exit 4 and cost no extra round trip."""
        calls = [
            completed(stderr=GH_AUTH_STATUS_INVALID, rc=1),
            completed(stderr=PROXY_GRAPHQL_403, rc=1),
            completed(stderr=BAD_CREDENTIALS, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls) as run:
            result = check_gh_auth()
        assert result.status is GhAuthStatus.INVALID_CREDENTIALS
        assert run.call_count == 3

    def test_graphql_blocked_is_not_reported_as_authenticated(self):
        calls = [*self._until_user_probe(), completed(stdout="{}", rc=0)]
        with patch("subprocess.run", side_effect=calls):
            assert not check_gh_auth().is_authenticated


class TestAssertRestOnly:
    """``rest_only`` lets REST-only scripts pass GRAPHQL_BLOCKED and nothing else."""

    def _assert_with(self, status: GhAuthStatus, **kwargs) -> None:
        with patch(
            "scripts.github_core.api.check_gh_auth",
            return_value=GhAuthResult(status),
        ):
            assert_gh_authenticated(**kwargs)

    def test_rest_only_passes_graphql_blocked(self):
        self._assert_with(GhAuthStatus.GRAPHQL_BLOCKED, rest_only=True)

    def test_default_still_fails_graphql_blocked_with_exit_2(self):
        with pytest.raises(SystemExit) as exc:
            self._assert_with(GhAuthStatus.GRAPHQL_BLOCKED)
        assert exc.value.code == 2

    @pytest.mark.parametrize(
        ("status", "code"),
        [
            (GhAuthStatus.TRANSPORT_BLOCKED, 2),
            (GhAuthStatus.INVALID_CREDENTIALS, 4),
            (GhAuthStatus.MISSING_GH, 4),
            (GhAuthStatus.RATE_LIMITED, 3),
            (GhAuthStatus.TRANSIENT_ERROR, 3),
        ],
    )
    def test_rest_only_still_fails_every_other_refusal(self, status, code):
        with pytest.raises(SystemExit) as exc:
            self._assert_with(status, rest_only=True)
        assert exc.value.code == code

    def test_authenticated_passes_either_way(self):
        self._assert_with(GhAuthStatus.AUTHENTICATED)
        self._assert_with(GhAuthStatus.AUTHENTICATED, rest_only=True)
