"""Tests for post_pr_comment_reply.py skill script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from scripts.github_core.api import RepoInfo

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


_mod = _import_script("post_pr_comment_reply")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--body", "test"])

    def test_body_and_body_file_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([
                "--pull-request", "1", "--body", "text", "--body-file", "f.md",
            ])

    def test_valid_inline_body(self):
        args = build_parser().parse_args([
            "--pull-request", "50", "--comment-id", "123", "--body", "Fixed.",
        ])
        assert args.pull_request == 50
        assert args.comment_id == 123
        assert args.body == "Fixed."


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "post_pr_comment_reply.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1", "--body", "test"])
            assert exc.value.code == 4

    def test_empty_body_exits_1(self):
        with patch(
            "post_pr_comment_reply.assert_gh_authenticated",
        ), patch(
            "post_pr_comment_reply.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1", "--body", ""])
            assert exc.value.code == 1

    def test_body_file_not_found_exits_2(self):
        with patch(
            "post_pr_comment_reply.assert_gh_authenticated",
        ), patch(
            "post_pr_comment_reply.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1", "--body-file", "/nonexistent/file.md"])
            assert exc.value.code == 2

    def test_body_file_path_traversal_exits_1(self):
        """CWE-22: Path traversal in body-file is rejected."""
        with patch(
            "post_pr_comment_reply.assert_gh_authenticated",
        ), patch(
            "post_pr_comment_reply.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1", "--body-file", "../../etc/passwd"])
            assert exc.value.code == 1

    def test_review_comment_reply_success(self, capsys):
        response = json.dumps({
            "id": 999, "html_url": "https://example.com", "created_at": "now",
        })
        with patch(
            "post_pr_comment_reply.assert_gh_authenticated",
        ), patch(
            "post_pr_comment_reply.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=response, rc=0),
        ):
            rc = main([
                "--pull-request", "50", "--comment-id", "123", "--body", "Fixed.",
            ])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["success"] is True
        assert output["in_reply_to"] == 123

    def test_top_level_comment_success(self, capsys):
        response = json.dumps({
            "id": 888, "html_url": "https://example.com", "created_at": "now",
        })
        with patch(
            "post_pr_comment_reply.assert_gh_authenticated",
        ), patch(
            "post_pr_comment_reply.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=response, rc=0),
        ):
            rc = main(["--pull-request", "50", "--body", "All addressed."])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["success"] is True
        assert output["in_reply_to"] is None

    def test_api_error_exits_3(self):
        with patch(
            "post_pr_comment_reply.assert_gh_authenticated",
        ), patch(
            "post_pr_comment_reply.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="API error"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1", "--body", "test"])
            assert exc.value.code == 3

    def test_body_from_file(self, tmp_path, capsys):
        body_file = tmp_path / "body.md"
        body_file.write_text("hello from file")
        response = json.dumps({
            "id": 777, "html_url": "https://example.com", "created_at": "now",
        })
        with patch(
            "post_pr_comment_reply.assert_gh_authenticated",
        ), patch(
            "post_pr_comment_reply.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=response, rc=0),
        ):
            rc = main([
                "--pull-request", "1", "--body-file", str(body_file),
            ])
        assert rc == 0
