"""Tests for get_pr_review_comments.py skill script."""

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


_mod = _import_script("get_pr_review_comments")
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
            build_parser().parse_args([])

    def test_valid_args(self):
        args = build_parser().parse_args(["--pull-request", "42"])
        assert args.pull_request == 42

    def test_bot_only_default_false(self):
        args = build_parser().parse_args(["--pull-request", "1"])
        assert args.bot_only is False

    def test_bot_only_requires_only_unaddressed(self):
        args = build_parser().parse_args(
            ["--pull-request", "1", "--only-unaddressed", "--bot-only"]
        )
        assert args.bot_only is True
        assert args.only_unaddressed is True

    def test_detect_stale(self):
        args = build_parser().parse_args(["--pull-request", "1", "--detect-stale"])
        assert args.detect_stale is True

    def test_group_by_domain(self):
        args = build_parser().parse_args(["--pull-request", "1", "--group-by-domain"])
        assert args.group_by_domain is True


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "get_pr_review_comments.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_no_comments(self, capsys):
        with patch(
            "get_pr_review_comments.assert_gh_authenticated",
        ), patch(
            "get_pr_review_comments.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_review_comments.gh_api_paginated",
            return_value=[],
        ), patch(
            "get_pr_review_comments.get_unresolved_review_threads",
            return_value=[],
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Success"] is True
        assert output["TotalComments"] == 0

    def test_bot_comment_included(self, capsys):
        raw_comments = [
            {
                "id": 100,
                "user": {"login": "coderabbit[bot]", "type": "Bot"},
                "body": "Consider adding a test",
                "path": "src/main.py",
                "line": 10,
                "original_line": 10,
                "reactions": {"eyes": 0},
                "in_reply_to_id": None,
                "created_at": "2024-01-01",
                "updated_at": "2024-01-01",
                "html_url": "https://example.com",
            },
        ]
        unresolved_threads = [
            {"comments": {"nodes": [{"databaseId": 100}]}},
        ]
        with patch(
            "get_pr_review_comments.assert_gh_authenticated",
        ), patch(
            "get_pr_review_comments.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_review_comments.gh_api_paginated",
            return_value=raw_comments,
        ), patch(
            "get_pr_review_comments.get_unresolved_review_threads",
            return_value=unresolved_threads,
        ):
            rc = main(["--pull-request", "42", "--only-unaddressed"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["TotalComments"] == 1
        assert output["Comments"][0]["Author"] == "coderabbit[bot]"

    def test_human_comment_filtered_with_bot_only(self, capsys):
        raw_comments = [
            {
                "id": 100,
                "user": {"login": "human", "type": "User"},
                "body": "Please fix this",
                "path": "src/main.py",
                "line": 10,
                "original_line": 10,
                "reactions": {"eyes": 0},
                "in_reply_to_id": None,
                "created_at": "2024-01-01",
                "updated_at": "2024-01-01",
                "html_url": "https://example.com",
            },
        ]
        with patch(
            "get_pr_review_comments.assert_gh_authenticated",
        ), patch(
            "get_pr_review_comments.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_review_comments.gh_api_paginated",
            return_value=raw_comments,
        ), patch(
            "get_pr_review_comments.get_unresolved_review_threads",
            return_value=[],
        ):
            rc = main(["--pull-request", "42", "--only-unaddressed", "--bot-only"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["TotalComments"] == 0
