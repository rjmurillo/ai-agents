"""Exit-code mapping and remedy text for gh auth failures (issues #3139, #4326).

Captured refusal bodies live in ``tests/gh_auth_refusal_fixtures.py``.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from scripts.github_core.api import (
    GhAuthResult,
    GhAuthStatus,
    assert_gh_authenticated,
    describe_gh_auth_failure,
)
from tests.gh_auth_refusal_fixtures import (
    BAD_CREDENTIALS,
    GH_CONNECT_FAILURE,
    GH_DIAL_FAILURE,
    GH_DNS_FAILURE,
    GRAPHQL_QUOTA,
    REST_403_QUOTA,
    REST_503,
    SECONDARY_LIMIT,
    completed,
)


class TestAssertGhAuthenticatedExitCodes:
    def test_success_does_not_exit(self):
        with patch("subprocess.run", return_value=completed(rc=0)):
            assert assert_gh_authenticated() is None

    @pytest.mark.parametrize("body", [REST_503, REST_403_QUOTA, SECONDARY_LIMIT])
    def test_upstream_conditions_exit_3(self, body, capsys):
        # Three gh calls: auth status, graphql probe, and the best-effort
        # rate_limit lookup that enriches a quota diagnostic.
        calls = [
            completed(stderr=body, rc=1),
            completed(stderr=body, rc=1),
            completed(stdout="{}", rc=0),
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
            completed(stderr=REST_403_QUOTA, rc=1),
            completed(stderr=GRAPHQL_QUOTA, rc=1),
            completed(stdout=payload, rc=0),
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
            completed(stderr=BAD_CREDENTIALS, rc=1),
            completed(stderr=BAD_CREDENTIALS, rc=1),
        ]
        with patch("subprocess.run", side_effect=calls):
            with pytest.raises(SystemExit) as exc:
                assert_gh_authenticated()
        assert exc.value.code == 4
        assert "gh auth login" in capsys.readouterr().err

    @pytest.mark.parametrize("body", [GH_DIAL_FAILURE, GH_CONNECT_FAILURE, GH_DNS_FAILURE])
    def test_lost_connectivity_exits_3_and_never_says_gh_auth_login(self, body, capsys):
        calls = [completed(stderr=body, rc=1), completed(stderr=body, rc=1)]
        with patch("subprocess.run", side_effect=calls):
            with pytest.raises(SystemExit) as exc:
                assert_gh_authenticated()
        assert exc.value.code == 3
        assert "gh auth login" not in capsys.readouterr().err


class TestTransportBlockedRemedy:
    """The message an agent reads decides its next call, so it must be true."""

    def _describe(self):
        return describe_gh_auth_failure(GhAuthResult(GhAuthStatus.TRANSPORT_BLOCKED, "HTTP 403"))

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
