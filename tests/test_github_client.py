"""Tests for GitHubClient protocol, GhCliClient, and client-injected API functions."""

from __future__ import annotations

import json
import subprocess
from typing import Any
from unittest.mock import patch

import pytest

from scripts.github_core import GhCliClient, GitHubClient
from scripts.github_core.api import create_issue_comment, get_issue_comments

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    """Build a CompletedProcess for mocking."""
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


class FakeGitHubClient:
    """In-memory stub satisfying GitHubClient via structural subtyping."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.responses: dict[tuple[str, str], Any] = {}

    def rest_get(self, endpoint: str) -> dict[str, Any]:
        self.calls.append(("GET", endpoint, None))
        return self.responses.get(("GET", endpoint), {})  # type: ignore[no-any-return]

    def rest_post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("POST", endpoint, payload))
        return self.responses.get(("POST", endpoint), {})  # type: ignore[no-any-return]

    def rest_patch(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("PATCH", endpoint, payload))
        return self.responses.get(("PATCH", endpoint), {})  # type: ignore[no-any-return]

    def graphql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.calls.append(("GRAPHQL", query, variables))
        return self.responses.get(("GRAPHQL", query), {})  # type: ignore[no-any-return]

    def is_authenticated(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_fake_client_satisfies_protocol(self):
        fake = FakeGitHubClient()
        assert isinstance(fake, GitHubClient)

    def test_gh_cli_client_satisfies_protocol(self):
        client = GhCliClient()
        assert isinstance(client, GitHubClient)


# ---------------------------------------------------------------------------
# GhCliClient: rest_get
# ---------------------------------------------------------------------------


class TestGhCliClientRestGet:
    def test_success_returns_parsed_json(self):
        data = {"id": 1, "body": "hello"}
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(data))):
            result = GhCliClient().rest_get("repos/o/r/issues/1/comments")
        assert result == data

    def test_failure_raises_runtime_error(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="Not Found"),
        ):
            with pytest.raises(RuntimeError, match="gh api GET.*failed"):
                GhCliClient().rest_get("repos/o/r/issues/999")


# ---------------------------------------------------------------------------
# GhCliClient: rest_post
# ---------------------------------------------------------------------------


class TestGhCliClientRestPost:
    def test_success_returns_parsed_json(self):
        response = {"id": 42, "body": "new"}
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=json.dumps(response)),
        ) as mock:
            result = GhCliClient().rest_post(
                "repos/o/r/issues/1/comments", {"body": "new"}
            )
        assert result == response
        assert mock.call_args.kwargs.get("input") == json.dumps({"body": "new"})

    def test_failure_raises_runtime_error(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="Forbidden"),
        ):
            with pytest.raises(RuntimeError, match="gh api POST.*failed"):
                GhCliClient().rest_post("repos/o/r/issues/1/comments", {"body": "x"})


class TestGhCliClientRestPostNoContent:
    """A successful POST that answers with no body is a success, not a failure.

    The Actions cancel endpoint answers ``202 Accepted`` with an empty body
    (https://docs.github.com/rest/actions/workflow-runs#cancel-a-workflow-run),
    so ``gh api`` writes nothing to stdout. Parsing that as JSON raised
    ``JSONDecodeError`` on a call that had already cancelled the run, and
    ``workflow_runs.cancel_runs`` catches ``ValueError``, so it recorded every
    successful cancellation as failed and the CLI exited 3 after mutating.
    """

    ACTIONS_CANCEL = "repos/o/r/actions/runs/12345/cancel"

    @pytest.mark.parametrize("body", ["", "\n", "   \n"])
    def test_an_empty_202_body_returns_an_empty_dict(self, body: str):
        with patch("subprocess.run", return_value=_completed(stdout=body)):
            assert GhCliClient().rest_post(self.ACTIONS_CANCEL, {}) == {}

    def test_a_non_empty_non_json_body_still_raises(self):
        """Control: only an empty body is a no-content success. A body that is
        present and unparseable is a malformed response and must stay loud.
        """
        with patch("subprocess.run", return_value=_completed(stdout="<html>502</html>")):
            with pytest.raises(ValueError, match="non-JSON body"):
                GhCliClient().rest_post(self.ACTIONS_CANCEL, {})

    def test_a_json_array_body_raises_rather_than_mistyping_the_return(self):
        with patch("subprocess.run", return_value=_completed(stdout="[1, 2]")):
            with pytest.raises(ValueError, match="expected an object"):
                GhCliClient().rest_post(self.ACTIONS_CANCEL, {})


# ---------------------------------------------------------------------------
# GhCliClient: rest_patch
# ---------------------------------------------------------------------------


class TestGhCliClientRestPatch:
    def test_success_returns_parsed_json(self):
        response = {"id": 1, "body": "updated"}
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=json.dumps(response)),
        ) as mock:
            result = GhCliClient().rest_patch(
                "repos/o/r/issues/comments/1", {"body": "updated"}
            )
        assert result == response
        assert mock.call_args.kwargs.get("input") == json.dumps({"body": "updated"})

    def test_failure_raises_runtime_error(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="Server Error"),
        ):
            with pytest.raises(RuntimeError, match="gh api PATCH.*failed"):
                GhCliClient().rest_patch(
                    "repos/o/r/issues/comments/1", {"body": "x"}
                )


# ---------------------------------------------------------------------------
# GhCliClient: graphql
# ---------------------------------------------------------------------------


class TestGhCliClientGraphql:
    def test_simple_query_returns_data(self):
        response = json.dumps({"data": {"viewer": {"login": "user"}}})
        with patch("subprocess.run", return_value=_completed(stdout=response)):
            result = GhCliClient().graphql("query { viewer { login } }")
        assert result == {"viewer": {"login": "user"}}

    def test_variables_passed_correctly(self):
        response = json.dumps({"data": {}})
        with patch("subprocess.run", return_value=_completed(stdout=response)) as mock:
            GhCliClient().graphql(
                "query($owner: String!, $num: Int!) { ... }",
                {"owner": "rjmurillo", "num": 42},
            )
        cmd = mock.call_args[0][0]
        assert "-f" in cmd
        assert "owner=rjmurillo" in cmd
        assert "-F" in cmd
        assert "num=42" in cmd

    def test_transport_error_raises(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="network error"),
        ):
            with pytest.raises(RuntimeError, match="GraphQL request failed"):
                GhCliClient().graphql("query { viewer { login } }")

    def test_graphql_level_errors_raise(self):
        response = json.dumps(
            {"data": None, "errors": [{"message": "Not found"}]}
        )
        with patch("subprocess.run", return_value=_completed(stdout=response)):
            with pytest.raises(RuntimeError, match="GraphQL errors.*Not found"):
                GhCliClient().graphql("query { ... }")


# ---------------------------------------------------------------------------
# GhCliClient: is_authenticated
# ---------------------------------------------------------------------------


class TestGhCliClientIsAuthenticated:
    def test_returns_true_when_authenticated(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assert GhCliClient().is_authenticated() is True

    def test_returns_false_when_not_authenticated(self):
        with patch("subprocess.run", return_value=_completed(rc=1)):
            assert GhCliClient().is_authenticated() is False

    def test_returns_false_when_gh_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert GhCliClient().is_authenticated() is False

    def test_returns_false_on_timeout(self):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30),
        ):
            assert GhCliClient().is_authenticated() is False

    def test_quota_refusal_is_not_reported_as_unauthenticated(self):
        """A 403 quota refusal is not proof of a bad token (issue #3139).

        `gh auth status` exits nonzero for a quota refusal, a 5xx, and a dead
        network as well as for a bad token. Reading only its return code made
        this method answer a GitHub outage with False, and the callers turned
        that into "run gh auth login".
        """
        refusal = _completed(
            rc=1, stderr="gh: API rate limit exceeded for user ID 6811113 (HTTP 403)"
        )
        viewer_ok = _completed(rc=0, stdout='{"data":{"viewer":{"login":"octocat"}}}')

        with patch("subprocess.run", side_effect=[refusal, viewer_ok]):
            assert GhCliClient().is_authenticated() is True

    def test_delegates_to_the_shared_classifier(self):
        """Wiring guard: the method must route through `api.is_gh_authenticated`.

        Without this, a future edit can reintroduce a local `returncode == 0`
        read here and every test above still passes, because those tests only
        observe the boolean.
        """
        with patch(
            "scripts.github_core.gh_client.is_gh_authenticated", return_value=True
        ) as delegate:
            assert GhCliClient().is_authenticated() is True

        assert delegate.call_count == 1


# ---------------------------------------------------------------------------
# get_issue_comments with client injection
# ---------------------------------------------------------------------------


class TestGetIssueCommentsWithClient:
    def test_uses_client_when_provided(self):
        fake = FakeGitHubClient()
        comments = [{"id": 1, "body": "hello"}]
        fake.responses[("GET", "repos/o/r/issues/42/comments")] = comments
        result = get_issue_comments("o", "r", 42, client=fake)
        assert result == comments
        assert len(fake.calls) == 1
        assert fake.calls[0] == ("GET", "repos/o/r/issues/42/comments", None)

    def test_falls_back_to_subprocess_when_no_client(self):
        comments = [{"id": 1, "body": "hello"}]
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=json.dumps(comments)),
        ):
            result = get_issue_comments("o", "r", 42)
        assert result == comments

    def test_wraps_dict_response_in_list(self):
        fake = FakeGitHubClient()
        fake.responses[("GET", "repos/o/r/issues/1/comments")] = {"id": 1}
        result = get_issue_comments("o", "r", 1, client=fake)
        assert result == [{"id": 1}]


# ---------------------------------------------------------------------------
# create_issue_comment with client injection
# ---------------------------------------------------------------------------


class TestCreateIssueCommentWithClient:
    def test_uses_client_when_provided(self):
        fake = FakeGitHubClient()
        response = {"id": 99, "body": "posted"}
        fake.responses[("POST", "repos/o/r/issues/42/comments")] = response
        result = create_issue_comment("o", "r", 42, "posted", client=fake)
        assert result == response
        assert len(fake.calls) == 1
        assert fake.calls[0] == (
            "POST",
            "repos/o/r/issues/42/comments",
            {"body": "posted"},
        )

    def test_falls_back_to_subprocess_when_no_client(self):
        response = {"id": 99, "body": "posted"}
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=json.dumps(response)),
        ):
            result = create_issue_comment("o", "r", 42, "posted")
        assert result == response

    def test_subprocess_failure_exits_3_without_client(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="API error"),
        ):
            with pytest.raises(SystemExit) as exc:
                create_issue_comment("o", "r", 42, "text")
            assert exc.value.code == 3


# ---------------------------------------------------------------------------
# GhCliClient: captured-text decoding
# ---------------------------------------------------------------------------


# `is_authenticated` is deliberately absent. It no longer runs a gh command of
# its own: it delegates to `github_core.api.is_gh_authenticated`, whose helper
# uses `errors="replace"` and a 10s timeout because an auth preflight is a
# diagnostic, not a payload the caller writes back to GitHub. The contract below
# governs calls that decode a body; `TestGhCliClientIsAuthenticated` pins the
# delegation instead.
_CAPTURING_CALLS = (
    ("rest_get", lambda c: c.rest_get("repos/o/r/issues/1")),
    ("rest_post", lambda c: c.rest_post("repos/o/r/issues/1/comments", {"body": "x"})),
    ("rest_patch", lambda c: c.rest_patch("repos/o/r/issues/1", {"state": "closed"})),
    ("graphql", lambda c: c.graphql("query { viewer { login } }")),
)


class TestGhCliClientDecoding:
    """`gh` emits raw UTF-8, so every captured-text call has to pin the codec.

    Without an explicit ``encoding``, Python decodes with the locale's
    preferred codec. On a cp1252 or cp932 runner the bytes still decode, into
    different characters, and ``json.loads`` accepts the result. The failure is
    silent: no exception, wrong text.
    """

    @pytest.mark.parametrize(
        ("name", "invoke"), _CAPTURING_CALLS, ids=[c[0] for c in _CAPTURING_CALLS]
    )
    def test_pins_utf8(self, name, invoke):
        with patch("subprocess.run", return_value=_completed(stdout="{}")) as run:
            invoke(GhCliClient())
        assert run.called, f"{name} did not invoke subprocess.run"
        assert run.call_args.kwargs.get("encoding") == "utf-8", f"{name} does not pin encoding"

    @pytest.mark.parametrize(
        ("name", "invoke"), _CAPTURING_CALLS, ids=[c[0] for c in _CAPTURING_CALLS]
    )
    def test_leaves_decode_errors_strict(self, name, invoke):
        """Undecodable bytes must raise, not become U+FFFD inside parsed JSON.

        ``json.loads`` accepts a replacement character without complaint, so a
        lenient error handler would hand the caller a silently corrupted body.
        The GitHub API emits valid UTF-8, so a decode failure means the stream
        is broken and the caller needs to hear about it.
        """
        with patch("subprocess.run", return_value=_completed(stdout="{}")) as run:
            invoke(GhCliClient())
        assert "errors" not in run.call_args.kwargs, f"{name} weakens strict decoding"

    @pytest.mark.parametrize(
        ("name", "invoke"), _CAPTURING_CALLS, ids=[c[0] for c in _CAPTURING_CALLS]
    )
    def test_keeps_the_timeout(self, name, invoke):
        """One helper now feeds every call, so a dropped timeout would hang all five."""
        with patch("subprocess.run", return_value=_completed(stdout="{}")) as run:
            invoke(GhCliClient())
        assert run.call_args.kwargs.get("timeout") == 30, f"{name} does not set a timeout"

    def test_real_api_bytes_survive_the_round_trip(self):
        """Bytes taken from a live `gh api` comment payload, not invented.

        cp1252 decodes the same bytes to 'ðŸ”´' and json.loads accepts it, so
        the assertion is on the decoded text, not on the absence of an error.
        """
        raw = b'{"body": "Semgrep identified a blocking \xf0\x9f\x94\xb4 issue"}'
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=raw.decode("utf-8")),
        ):
            result = GhCliClient().rest_get("repos/o/r/issues/1")
        assert result["body"] == "Semgrep identified a blocking \U0001f534 issue"
        assert "\u00f0\u0178" not in result["body"]
