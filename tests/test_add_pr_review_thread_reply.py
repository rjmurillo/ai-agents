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
            return_value=reply_data,
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "Fixed."])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["success"] is True
        assert output["comment_id"] == 456
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
        with patch(
            "add_pr_review_thread_reply.assert_gh_authenticated",
        ), patch(
            "add_pr_review_thread_reply.gh_graphql",
            side_effect=[reply_data, resolve_data],
        ):
            rc = main(["--thread-id", "PRRT_abc", "--body", "Fixed.", "--resolve"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["thread_resolved"] is True

    def test_thread_not_found_exits_2(self):
        with patch(
            "add_pr_review_thread_reply.assert_gh_authenticated",
        ), patch(
            "add_pr_review_thread_reply.gh_graphql",
            side_effect=RuntimeError("Could not resolve to a node"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--thread-id", "PRRT_abc", "--body", "test"])
            assert exc.value.code == 2

    def test_api_error_exits_3(self):
        with patch(
            "add_pr_review_thread_reply.assert_gh_authenticated",
        ), patch(
            "add_pr_review_thread_reply.gh_graphql",
            side_effect=RuntimeError("Server error"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--thread-id", "PRRT_abc", "--body", "test"])
            assert exc.value.code == 3

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
        with patch(
            "add_pr_review_thread_reply.assert_gh_authenticated",
        ), patch(
            "add_pr_review_thread_reply.gh_graphql",
            return_value=reply_data,
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
