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
        self.responses: dict[str, Any] = {}

    def rest_get(self, endpoint: str) -> dict[str, Any]:
        self.calls.append(("GET", endpoint, None))
        return self.responses.get(("GET", endpoint), {})

    def rest_post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("POST", endpoint, payload))
        return self.responses.get(("POST", endpoint), {})

    def rest_patch(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("PATCH", endpoint, payload))
        return self.responses.get(("PATCH", endpoint), {})

    def graphql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.calls.append(("GRAPHQL", query, variables))
        return self.responses.get(("GRAPHQL", query), {})

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
