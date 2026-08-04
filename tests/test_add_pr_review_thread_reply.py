"""Tests for add_pr_review_thread_reply.py skill script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("add_pr_review_thread_reply")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_thread_id_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--body", "test"])

    def test_body_and_body_file_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([
                "--thread-id", "PRRT_abc", "--body", "text", "--body-file", "f.md",
            ])

    def test_valid_args(self):
        args = build_parser().parse_args([
            "--thread-id", "PRRT_abc", "--body", "Fixed.",
        ])
        assert args.thread_id == "PRRT_abc"
        assert args.body == "Fixed."


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_invalid_thread_id_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            main(["--thread-id", "INVALID_123", "--body", "test"])
        assert exc.value.code == 2

    def test_empty_body_exits_2(self):
        with patch(
            "add_pr_review_thread_reply.assert_gh_authenticated",
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--thread-id", "PRRT_abc", "--body", ""])
        assert exc.value.code == 2

    def test_not_authenticated_exits_4(self):
        with patch(
            "add_pr_review_thread_reply.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--thread-id", "PRRT_abc", "--body", "test"])
            assert exc.value.code == 4

    def test_reply_success(self, capsys):
        state_data = {"node": {"id": "PRRT_abc", "isResolved": False}}
        reply_data = {
            "addPullRequestReviewThreadReply": {
                "comment": {
                    "id": "node123",
                    "databaseId": 456,
                    "url": "https://example.com",
                    "createdAt": "2025-01-01T00:00:00Z",
                    "author": {"login": "user1"},
                },
            },
        }
        with patch(
            "add_pr_review_thread_reply.assert_gh_authenticated",
        ), patch(
            "add_pr_review_thread_reply.gh_graphql",
            side_effect=[state_data, reply_data],
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "Fixed."])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["comment_node_id"] == "node123"
        assert output["thread_resolved"] is False

    def test_reply_with_resolve(self, capsys):
        state_data = {"node": {"id": "PRRT_abc", "isResolved": False}}
        reply_data = {
            "addPullRequestReviewThreadReply": {
                "comment": {
                    "id": "node123",
                    "databaseId": 456,
                    "url": "https://example.com",
                    "createdAt": "2025-01-01T00:00:00Z",
                    "author": {"login": "user1"},
                },
            },
        }
        resolve_data = {
            "resolveReviewThread": {
                "thread": {"id": "PRRT_abc", "isResolved": True},
            },
        }
        with patch(
            "add_pr_review_thread_reply.assert_gh_authenticated",
        ), patch(
            "add_pr_review_thread_reply.gh_graphql",
            side_effect=[state_data, reply_data, resolve_data],
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "Fixed.", "--resolve"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["thread_resolved"] is True

    def test_thread_not_found_exits_0_skip(self, capsys):
        # After #3930 gate: a state-query "not found" returns SKIP (exit 0).
        # The thread was deleted or concurrently resolved before we could act.
        with patch(
            "add_pr_review_thread_reply.assert_gh_authenticated",
        ), patch(
            "add_pr_review_thread_reply.gh_graphql",
            side_effect=RuntimeError("Could not resolve to a node"),
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "test"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["action"] == "SKIP"

    def test_api_error_exits_0_skip(self, capsys):
        # After #3930 gate: a transient API error in the state query returns SKIP (exit 0).
        with patch(
            "add_pr_review_thread_reply.assert_gh_authenticated",
        ), patch(
            "add_pr_review_thread_reply.gh_graphql",
            side_effect=RuntimeError("Server error"),
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "test"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["action"] == "SKIP"

    def test_body_from_file(self, tmp_path, capsys):
        body_file = tmp_path / "reply.md"
        body_file.write_text("File content")
        state_data = {"node": {"id": "PRRT_abc", "isResolved": False}}
        reply_data = {
            "addPullRequestReviewThreadReply": {
                "comment": {
                    "id": "n1",
                    "databaseId": 1,
                    "url": "https://example.com",
                    "createdAt": "now",
                    "author": {"login": "me"},
                },
            },
        }
        with patch(
            "add_pr_review_thread_reply.assert_gh_authenticated",
        ), patch(
            "add_pr_review_thread_reply.gh_graphql",
            side_effect=[state_data, reply_data],
        ), patch(
            "github_core.validation.assert_valid_body_file",
        ):
            rc = main([
                "--thread-id", "PRRT_abc", "--body-file", str(body_file),
            ])
        assert rc == 0

    def test_body_file_not_found_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            main([
                "--thread-id", "PRRT_abc", "--body-file", "/nonexistent/file.md",
            ])
        assert exc.value.code == 2

    def test_body_file_path_traversal_exits_2(self):
        """CWE-22: Path traversal in body-file is rejected."""
        with pytest.raises(SystemExit) as exc:
            main([
                "--thread-id", "PRRT_abc",
                "--body-file", "../../etc/passwd",
            ])
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Issue #3930: thread-state gate (pre-mutation requery)
# ---------------------------------------------------------------------------

_query_thread_state = _mod._query_thread_state


class TestQueryThreadStateReply:
    """Unit tests for the pre-mutation state query in add_pr_review_thread_reply."""

    def test_unresolved_thread_returns_act(self):
        with patch(
            "add_pr_review_thread_reply.gh_graphql",
            return_value={"node": {"id": "PRRT_abc", "isResolved": False}},
        ):
            result = _query_thread_state("PRRT_abc")
        assert result["action"] == "ACT"

    def test_resolved_thread_returns_skip(self):
        with patch(
            "add_pr_review_thread_reply.gh_graphql",
            return_value={"node": {"id": "PRRT_abc", "isResolved": True}},
        ):
            result = _query_thread_state("PRRT_abc")
        assert result["action"] == "SKIP"

    def test_missing_thread_returns_skip(self):
        with patch(
            "add_pr_review_thread_reply.gh_graphql",
            return_value={"node": None},
        ):
            result = _query_thread_state("PRRT_abc")
        assert result["action"] == "SKIP"

    def test_api_error_returns_skip(self):
        with patch(
            "add_pr_review_thread_reply.gh_graphql",
            side_effect=RuntimeError("API failure"),
        ):
            result = _query_thread_state("PRRT_abc")
        assert result["action"] == "SKIP"
        assert "failed" in result["reason"]


class TestMainReplyThreadStateConcurrency:
    """Reply is skipped when thread is resolved concurrently."""

    def test_resolved_thread_skips_mutation(self, capsys, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("comment text")

        graphql_calls = []

        def _graphql_side_effect(query, variables):
            graphql_calls.append(variables)
            if "node(id:" in query:
                return {"node": {"id": variables["threadId"], "isResolved": True}}
            return {"addPullRequestReviewThreadReply": {"comment": {"id": "C_abc"}}}

        with patch(
            "add_pr_review_thread_reply.assert_gh_authenticated",
        ), patch(
            "add_pr_review_thread_reply.gh_graphql",
            side_effect=_graphql_side_effect,
        ), patch(
            "github_core.validation.assert_valid_body_file",
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body-file", str(body_file)])

        assert rc == 0
        out = capsys.readouterr().out
        output = json.loads(out)
        assert output["action"] == "SKIP"
        # Only the state query ran, no mutation
        assert len(graphql_calls) == 1

    def test_unresolved_thread_proceeds_to_mutation(self, capsys, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("comment text")

        reply_data = {
            "addPullRequestReviewThreadReply": {
                "comment": {"id": "C_abc", "url": "https://github.com/r/r/pull/1#comment"},
            },
        }

        def _graphql_side_effect(query, variables):
            if "node(id:" in query:
                return {"node": {"id": variables["threadId"], "isResolved": False}}
            return reply_data

        with patch(
            "add_pr_review_thread_reply.assert_gh_authenticated",
        ), patch(
            "add_pr_review_thread_reply.gh_graphql",
            side_effect=_graphql_side_effect,
        ), patch(
            "github_core.validation.assert_valid_body_file",
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body-file", str(body_file)])

        assert rc == 0
        out = capsys.readouterr().out
        output = json.loads(out)
        assert "comment_node_id" in output
