"""Auth verification for the ai-review action classifies before it accuses.

`scripts/ci/verify_github_auth.py` runs at `.github/actions/ai-review/action.yml`
ahead of the context build. It read only `gh auth status`'s exit code and
answered every nonzero with "Ensure bot-pat has valid token with required
scopes", which sends an operator to rotate a working secret during a GitHub
outage or a quota window. That is issue #3139.
"""

from __future__ import annotations

import pytest

from scripts.ci.verify_github_auth import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_LOGIC,
    EXIT_OK,
    CommandResult,
    verify_github_auth,
)

QUOTA_403 = "gh: API rate limit exceeded for user ID 6811113 (HTTP 403)"
UNICORN_503 = "HTTP 503: Service unavailable (https://api.github.com/user)"
LOST_NETWORK = (
    "error connecting to api.github.com\n"
    "check your internet connection or https://githubstatus.com"
)
BAD_TOKEN = "HTTP 401: Bad credentials (https://api.github.com/user)"
# Captured from a Claude Code remote session proxy on 2026-09-03, gh 2.98.0.
SESSION_REFUSAL = (
    "gh: GitHub access is not enabled for this session. An org admin must "
    "connect the Claude GitHub App for this organization. (HTTP 403)"
)


def _runner(*results: CommandResult):
    queue = list(results)

    def run(_argv):
        return queue.pop(0)

    return run


def _ok() -> CommandResult:
    return CommandResult(returncode=0, stdout="ok", stderr="")


def _failed(stderr: str) -> CommandResult:
    return CommandResult(returncode=1, stdout="", stderr=stderr)


class TestAuthStatusStage:
    def test_success_returns_zero(self):
        assert verify_github_auth(_runner(_ok(), _ok())) == EXIT_OK

    def test_bad_token_still_names_the_scopes(self, capsys):
        rc = verify_github_auth(_runner(_failed(BAD_TOKEN)))

        assert rc == EXIT_LOGIC
        assert "required scopes" in capsys.readouterr().out

    @pytest.mark.parametrize("body", [QUOTA_403, UNICORN_503, LOST_NETWORK])
    def test_upstream_conditions_are_external_and_do_not_blame_the_secret(
        self, body, capsys
    ):
        rc = verify_github_auth(_runner(_failed(body)))

        out = capsys.readouterr().out
        assert rc == EXIT_EXTERNAL
        assert "bot-pat" not in out
        assert "not an authentication failure" in out


class TestApiAccessStage:
    def test_permission_denial_still_names_the_repo_scope(self, capsys):
        rc = verify_github_auth(
            _runner(_ok(), _failed("HTTP 403: Resource not accessible by integration"))
        )

        assert rc == EXIT_LOGIC
        assert "'repo' scope" in capsys.readouterr().out

    @pytest.mark.parametrize("body", [QUOTA_403, UNICORN_503])
    def test_upstream_conditions_are_external(self, body, capsys):
        rc = verify_github_auth(_runner(_ok(), _failed(body)))

        out = capsys.readouterr().out
        assert rc == EXIT_EXTERNAL
        assert "bot-pat" not in out


class TestSessionRefusalIsNotRetryable:
    """A refused session has no reset, so it must not carry the retry signal.

    The branch printed the right words while still returning EXIT_EXTERNAL,
    which is exactly the signal that tells a caller to try again (Copilot
    review on PR #5509). Exit code and wording have to agree.
    """

    def test_session_refusal_exits_config_not_external(self, capsys):
        rc = verify_github_auth(_runner(_failed(SESSION_REFUSAL)))

        out = capsys.readouterr().out
        assert rc == EXIT_CONFIG
        assert "retrying will not clear it" in out
        assert "Retry shortly" not in out
        assert "bot-pat" not in out

    def test_api_access_stage_refusal_also_exits_config(self, capsys):
        """The second entry path reaches the same classifier."""
        rc = verify_github_auth(_runner(_ok(), _failed(SESSION_REFUSAL)))

        assert rc == EXIT_CONFIG
        assert "retrying will not clear it" in capsys.readouterr().out

    def test_a_quota_refusal_keeps_the_retry_signal(self, capsys):
        """Negative control: the retryable path is unchanged."""
        rc = verify_github_auth(_runner(_failed(QUOTA_403)))

        out = capsys.readouterr().out
        assert rc == EXIT_EXTERNAL
        assert "Retry shortly" in out
