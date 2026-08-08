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
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
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
query_thread_state = _mod.query_thread_state

_UNRESOLVED_STATE: dict = {
    "id": "PRRT_abc",
    "isResolved": False,
    "pullRequest": {"number": 42},
}
_AUTO_MERGE_GUARD_NOOP: dict = {
    "action": "NOOP",
    "reason": "auto_merge_not_armed",
}


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_thread_id_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--body", "test"])

    def test_body_and_body_file_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(
                [
                    "--thread-id",
                    "PRRT_abc",
                    "--body",
                    "text",
                    "--body-file",
                    "f.md",
                ]
            )

    def test_valid_args(self):
        args = build_parser().parse_args(
            [
                "--thread-id",
                "PRRT_abc",
                "--body",
                "Fixed.",
            ]
        )
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
        with (
            patch(
                "add_pr_review_thread_reply.assert_gh_authenticated",
            ),
            patch(
                "add_pr_review_thread_reply.query_thread_state",
                return_value=_UNRESOLVED_STATE,
            ),
            patch(
                "add_pr_review_thread_reply.gh_graphql",
                return_value=reply_data,
            ),
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "Fixed."])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)["Data"]
        assert output["action"] == "ACT"
        assert output["success"] is True
        assert output["comment_id"] == 456
        assert output["comment_node_id"] == "node123"
        assert output["thread_resolved"] is False

    def test_reply_with_resolve(self, capsys):
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
        with (
            patch(
                "add_pr_review_thread_reply.assert_gh_authenticated",
            ),
            patch(
                "add_pr_review_thread_reply.query_thread_state",
                return_value=_UNRESOLVED_STATE,
            ),
            patch(
                "add_pr_review_thread_reply.guard_auto_merge_before_final_thread_resolution",
                return_value=_AUTO_MERGE_GUARD_NOOP,
            ),
            patch(
                "add_pr_review_thread_reply.gh_graphql",
                side_effect=[reply_data, resolve_data],
            ),
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "Fixed.", "--resolve"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)["Data"]
        assert output["thread_resolved"] is True
        assert output["auto_merge_guard"] == _AUTO_MERGE_GUARD_NOOP

    def test_reply_resolve_guards_auto_merge_before_resolving(self, capsys):
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
        calls: list[str] = []

        def fake_graphql(query: str, variables: dict):
            if "addPullRequestReviewThreadReply" in query:
                calls.append("reply")
                return reply_data
            if "resolveReviewThread" in query:
                calls.append("resolve")
                return resolve_data
            raise AssertionError(query[:80])

        def fake_guard(thread_id: str) -> dict:
            calls.append("guard")
            assert thread_id == "PRRT_abc"
            return {"action": "DISABLED"}

        with (
            patch(
                "add_pr_review_thread_reply.assert_gh_authenticated",
            ),
            patch(
                "add_pr_review_thread_reply.query_thread_state",
                return_value=_UNRESOLVED_STATE,
            ),
            patch(
                "add_pr_review_thread_reply.guard_auto_merge_before_final_thread_resolution",
                side_effect=fake_guard,
            ),
            patch(
                "add_pr_review_thread_reply.gh_graphql",
                side_effect=fake_graphql,
            ),
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "Fixed.", "--resolve"])

        assert rc == 0
        assert calls == ["reply", "guard", "resolve"]
        output = json.loads(capsys.readouterr().out)["Data"]
        assert output["thread_resolved"] is True
        assert output["auto_merge_guard"]["action"] == "DISABLED"

    def test_external_resolution_after_reply_skips_resolve(self, capsys):
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
        resolved_state = {
            "id": "PRRT_abc",
            "isResolved": True,
            "pullRequest": {"number": 42},
        }
        with (
            patch(
                "add_pr_review_thread_reply.assert_gh_authenticated",
            ),
            patch(
                "add_pr_review_thread_reply.query_thread_state",
                side_effect=[_UNRESOLVED_STATE, resolved_state],
            ),
            patch(
                "add_pr_review_thread_reply.guard_auto_merge_before_final_thread_resolution",
            ) as guard,
            patch(
                "add_pr_review_thread_reply.gh_graphql",
                return_value=reply_data,
            ) as graphql,
        ):
            rc = main([
                "--thread-id",
                "PRRT_abc",
                "--pull-request",
                "42",
                "--body",
                "Fixed.",
                "--resolve",
            ])
        assert rc == 0
        assert graphql.call_count == 1
        guard.assert_not_called()
        output = json.loads(capsys.readouterr().out)["Data"]
        assert output["resolve_action"] == "SKIP"
        assert output["resolve_reason"] == "thread_resolved"
        assert output["thread_resolved"] is True

    def test_guard_failure_leaves_thread_unresolved(self):
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
        calls: list[str] = []

        def fake_graphql(query: str, variables: dict):
            if "addPullRequestReviewThreadReply" in query:
                calls.append("reply")
                return reply_data
            if "resolveReviewThread" in query:
                calls.append("resolve")
                return {}
            raise AssertionError(query[:80])

        with (
            patch(
                "add_pr_review_thread_reply.assert_gh_authenticated",
            ),
            patch(
                "add_pr_review_thread_reply.query_thread_state",
                return_value=_UNRESOLVED_STATE,
            ),
            patch(
                "add_pr_review_thread_reply.guard_auto_merge_before_final_thread_resolution",
                side_effect=RuntimeError("pagination incomplete"),
            ),
            patch(
                "add_pr_review_thread_reply.gh_graphql",
                side_effect=fake_graphql,
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--thread-id", "PRRT_abc", "--body", "Fixed.", "--resolve"])

        assert exc.value.code == 3
        assert calls == ["reply"]

    def test_thread_not_found_exits_0_skip(self, capsys):
        with (
            patch(
                "add_pr_review_thread_reply.assert_gh_authenticated",
            ),
            patch(
                "add_pr_review_thread_reply.query_thread_state",
                return_value=None,
            ),
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "test"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)["Data"]
        assert out["action"] == "SKIP"
        assert out["reason"] == "not_found"

    def test_api_error_exits_3(self, capsys):
        with (
            patch(
                "add_pr_review_thread_reply.assert_gh_authenticated",
            ),
            patch(
                "add_pr_review_thread_reply.query_thread_state",
                side_effect=RuntimeError("Server error"),
            ),
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "test"])
        assert rc == 3
        output = json.loads(capsys.readouterr().out)["Data"]
        assert output["action"] == "SKIP"
        assert output["reason"] == "thread_state_query_failed"

    def test_body_from_file(self, tmp_path, capsys):
        body_file = tmp_path / "reply.md"
        body_file.write_text("File content")
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
        with (
            patch(
                "add_pr_review_thread_reply.assert_gh_authenticated",
            ),
            patch(
                "add_pr_review_thread_reply.query_thread_state",
                return_value=_UNRESOLVED_STATE,
            ),
            patch(
                "add_pr_review_thread_reply.guard_auto_merge_before_final_thread_resolution",
                return_value=_AUTO_MERGE_GUARD_NOOP,
            ),
            patch(
                "add_pr_review_thread_reply.gh_graphql",
                return_value=reply_data,
            ),
            patch(
                "github_core.validation.assert_valid_body_file",
            ),
        ):
            rc = main(
                [
                    "--thread-id",
                    "PRRT_abc",
                    "--body-file",
                    str(body_file),
                ]
            )
        assert rc == 0

    def test_body_file_not_found_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            main(
                [
                    "--thread-id",
                    "PRRT_abc",
                    "--body-file",
                    "/nonexistent/file.md",
                ]
            )
        assert exc.value.code == 2

    def test_body_file_path_traversal_exits_2(self):
        """CWE-22: Path traversal in body-file is rejected."""
        with pytest.raises(SystemExit) as exc:
            main(
                [
                    "--thread-id",
                    "PRRT_abc",
                    "--body-file",
                    "../../etc/passwd",
                ]
            )
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Tests: query_thread_state
# ---------------------------------------------------------------------------


class TestQueryThreadState:
    def test_returns_thread_dict_when_found(self):
        node = {"id": "PRRT_abc", "isResolved": False}
        with patch(
            "add_pr_review_thread_reply.gh_graphql",
            return_value={"node": node},
        ):
            result = query_thread_state("PRRT_abc")
        assert result == node

    def test_returns_none_when_not_found(self):
        with patch(
            "add_pr_review_thread_reply.gh_graphql",
            return_value={"node": None},
        ):
            result = query_thread_state("PRRT_missing")
        assert result is None

    def test_propagates_api_error(self):
        with patch(
            "add_pr_review_thread_reply.gh_graphql",
            side_effect=RuntimeError("network error"),
        ):
            with pytest.raises(RuntimeError, match="network error"):
                query_thread_state("PRRT_abc")
