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

_UNRESOLVED_STATE: dict = {"id": "PRRT_abc", "isResolved": False}


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
        output = json.loads(capsys.readouterr().out)
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
                "add_pr_review_thread_reply.gh_graphql",
                side_effect=[reply_data, resolve_data],
            ),
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "Fixed.", "--resolve"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["thread_resolved"] is True

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
        out = json.loads(capsys.readouterr().out)
        assert out["action"] == "SKIP"
        assert out["reason"] == "not_found"

    def test_api_error_exits_0_skip(self, capsys):
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
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["action"] == "SKIP"

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


# ---------------------------------------------------------------------------
# Tests: thread state pre-check in main
# ---------------------------------------------------------------------------


class TestThreadStatePrecheck:
    def test_resolved_thread_returns_skip_exit_0(self, capsys):
        resolved_state = {"id": "PRRT_abc", "isResolved": True}
        with (
            patch(
                "add_pr_review_thread_reply.assert_gh_authenticated",
            ),
            patch(
                "add_pr_review_thread_reply.query_thread_state",
                return_value=resolved_state,
            ),
            patch(
                "add_pr_review_thread_reply.gh_graphql",
            ) as mock_gql,
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "test"])
        assert rc == 0
        mock_gql.assert_not_called()
        out = json.loads(capsys.readouterr().out)
        assert out["action"] == "SKIP"
        assert out["reason"] == "thread_resolved"

    def test_not_found_thread_returns_skip_exit_0(self, capsys):
        with (
            patch(
                "add_pr_review_thread_reply.assert_gh_authenticated",
            ),
            patch(
                "add_pr_review_thread_reply.query_thread_state",
                return_value=None,
            ),
            patch(
                "add_pr_review_thread_reply.gh_graphql",
            ) as mock_gql,
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "test"])
        assert rc == 0
        mock_gql.assert_not_called()
        out = json.loads(capsys.readouterr().out)
        assert out["action"] == "SKIP"
        assert out["reason"] == "not_found"

    def test_unresolved_thread_proceeds_to_act(self, capsys):
        reply_data = {
            "addPullRequestReviewThreadReply": {
                "comment": {
                    "id": "n1",
                    "databaseId": 99,
                    "url": "https://example.com",
                    "createdAt": "2025-01-01T00:00:00Z",
                    "author": {"login": "bot"},
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
            rc = main(["--thread-id", "PRRT_abc", "--body", "LGTM"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["action"] == "ACT"
        assert out["success"] is True

    def test_precheck_api_error_returns_skip_exit_0(self, capsys):
        with (
            patch(
                "add_pr_review_thread_reply.assert_gh_authenticated",
            ),
            patch(
                "add_pr_review_thread_reply.query_thread_state",
                side_effect=RuntimeError("API unavailable"),
            ),
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "test"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["action"] == "SKIP"
