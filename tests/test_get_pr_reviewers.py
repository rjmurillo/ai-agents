"""Tests for get_pr_reviewers.py skill script."""

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


_mod = _import_script("get_pr_reviewers")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _pr_json(author: str = "alice", review_requests=None, reviews=None):
    return json.dumps({
        "author": {"login": author},
        "reviewRequests": review_requests or [],
        "reviews": reviews or [],
    })


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_flags(self):
        args = build_parser().parse_args([
            "--pull-request", "10", "--exclude-bots", "--exclude-author",
        ])
        assert args.pull_request == 10
        assert args.exclude_bots is True
        assert args.exclude_author is True


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "get_pr_reviewers.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_pr_not_found_exits_2(self):
        with patch(
            "get_pr_reviewers.assert_gh_authenticated",
        ), patch(
            "get_pr_reviewers.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="not found"),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "999"])
            assert exc.value.code == 2

    def test_success_with_reviewers(self, capsys):
        pr_data = _pr_json(
            author="alice",
            reviews=[{"author": {"login": "bob"}}],
        )
        with patch(
            "get_pr_reviewers.assert_gh_authenticated",
        ), patch(
            "get_pr_reviewers.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=pr_data, rc=0),
        ), patch(
            "get_pr_reviewers.gh_api_paginated",
            return_value=[],
        ):
            rc = main(["--pull-request", "10"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["success"] is True
        assert output["total_reviewers"] == 1

    def test_exclude_bots_filters_bots(self, capsys):
        pr_data = _pr_json(author="alice")
        review_comments = [
            {"user": {"login": "bot-user[bot]", "type": "Bot"}},
            {"user": {"login": "human", "type": "User"}},
        ]
        with patch(
            "get_pr_reviewers.assert_gh_authenticated",
        ), patch(
            "get_pr_reviewers.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=pr_data, rc=0),
        ), patch(
            "get_pr_reviewers.gh_api_paginated",
            side_effect=[review_comments, []],
        ):
            rc = main(["--pull-request", "10", "--exclude-bots"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["human_count"] == 1
        logins = [r["login"] for r in output["reviewers"]]
        assert "bot-user[bot]" not in logins

    def test_exclude_author_filters_author(self, capsys):
        pr_data = _pr_json(author="alice")
        issue_comments = [
            {"user": {"login": "alice", "type": "User"}},
            {"user": {"login": "bob", "type": "User"}},
        ]
        with patch(
            "get_pr_reviewers.assert_gh_authenticated",
        ), patch(
            "get_pr_reviewers.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "subprocess.run",
            return_value=_completed(stdout=pr_data, rc=0),
        ), patch(
            "get_pr_reviewers.gh_api_paginated",
            side_effect=[[], issue_comments],
        ):
            rc = main(["--pull-request", "10", "--exclude-author"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        logins = [r["login"] for r in output["reviewers"]]
        assert "alice" not in logins
        assert "bob" in logins
