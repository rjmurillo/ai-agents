"""Tests for get_pr_comments_by_reviewer.py skill script."""

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


_mod = _import_script("get_pr_comments_by_reviewer")
main = _mod.main
build_parser = _mod.build_parser
get_pr_comments_by_reviewer = _mod.get_pr_comments_by_reviewer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODULE = "get_pr_comments_by_reviewer"


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _make_review_comment(
    login: str = "reviewer1",
    body: str = "Fix this",
    created_at: str = "2025-06-01T00:00:00Z",
    path: str = "src/main.py",
    user_type: str = "User",
):
    return {
        "user": {"login": login, "type": user_type},
        "body": body,
        "created_at": created_at,
        "updated_at": created_at,
        "path": path,
        "html_url": "https://github.com/o/r/pull/1#comment",
    }


def _make_issue_comment(
    login: str = "reviewer1",
    body: str = "Looks good",
    created_at: str = "2025-06-01T00:00:00Z",
    user_type: str = "User",
):
    return {
        "user": {"login": login, "type": user_type},
        "body": body,
        "created_at": created_at,
        "updated_at": created_at,
        "html_url": "https://github.com/o/r/pull/1#issuecomment",
    }


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_single_pr(self):
        args = build_parser().parse_args(["--pull-request", "42"])
        assert args.pull_request == [42]

    def test_multiple_prs(self):
        args = build_parser().parse_args(["--pull-request", "1", "2", "3"])
        assert args.pull_request == [1, 2, 3]

    def test_include_reviewer(self):
        args = build_parser().parse_args(
            ["--pull-request", "1", "--include-reviewer", "alice", "bob"]
        )
        assert args.include_reviewer == ["alice", "bob"]

    def test_exclude_reviewer(self):
        args = build_parser().parse_args(
            ["--pull-request", "1", "--exclude-reviewer", "bot1"]
        )
        assert args.exclude_reviewer == ["bot1"]

    def test_comment_type_default(self):
        args = build_parser().parse_args(["--pull-request", "1"])
        assert args.comment_type == "all"

    def test_comment_type_review_only(self):
        args = build_parser().parse_args(
            ["--pull-request", "1", "--comment-type", "review"]
        )
        assert args.comment_type == "review"

    def test_include_self_comments_default_false(self):
        args = build_parser().parse_args(["--pull-request", "1"])
        assert args.include_self_comments is False

    def test_since_until(self):
        args = build_parser().parse_args(
            ["--pull-request", "1", "--since", "2025-01-01", "--until", "2025-06-30"]
        )
        assert args.since == "2025-01-01"
        assert args.until == "2025-06-30"


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            f"{_MODULE}.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_no_comments(self, capsys):
        pr_view = _completed(stdout=json.dumps({"author": {"login": "author1"}}))
        with patch(
            f"{_MODULE}.assert_gh_authenticated",
        ), patch(
            f"{_MODULE}.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            f"{_MODULE}.subprocess.run",
            return_value=pr_view,
        ), patch(
            f"{_MODULE}.gh_api_paginated",
            return_value=[],
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["success"] is True
        assert output["total_comments"] == 0
        assert output["total_reviewers"] == 0

    def test_groups_by_reviewer(self, capsys):
        pr_view = _completed(stdout=json.dumps({"author": {"login": "author1"}}))
        review_comments = [
            _make_review_comment("alice", "Fix bug"),
            _make_review_comment("bob", "Add test"),
            _make_review_comment("alice", "Check style"),
        ]
        with patch(
            f"{_MODULE}.assert_gh_authenticated",
        ), patch(
            f"{_MODULE}.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            f"{_MODULE}.subprocess.run",
            return_value=pr_view,
        ), patch(
            f"{_MODULE}.gh_api_paginated",
            return_value=review_comments,
        ):
            rc = main(["--pull-request", "1", "--comment-type", "review"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["total_reviewers"] == 2
        assert output["total_comments"] == 3
        # Sorted by count descending: alice(2), bob(1)
        assert output["reviewers"][0]["login"] == "alice"
        assert output["reviewers"][0]["total_comments"] == 2
        assert output["reviewers"][1]["login"] == "bob"
        assert output["reviewers"][1]["total_comments"] == 1


# ---------------------------------------------------------------------------
# Tests: get_pr_comments_by_reviewer (unit)
# ---------------------------------------------------------------------------


class TestGetPrCommentsByReviewer:
    def _run(self, review_comments=None, issue_comments=None, pr_author="author1", **kwargs):
        review_comments = review_comments or []
        issue_comments = issue_comments or []
        pr_view = _completed(stdout=json.dumps({"author": {"login": pr_author}}))

        def paginated_side_effect(endpoint, **_kw):
            if "/pulls/" in endpoint and "/comments" in endpoint:
                return review_comments
            if "/issues/" in endpoint and "/comments" in endpoint:
                return issue_comments
            return []

        with patch(
            f"{_MODULE}.subprocess.run",
            return_value=pr_view,
        ), patch(
            f"{_MODULE}.gh_api_paginated",
            side_effect=paginated_side_effect,
        ):
            return get_pr_comments_by_reviewer("o", "r", [1], **kwargs)

    def test_excludes_self_comments(self):
        result = self._run(
            review_comments=[_make_review_comment("author1", "Self comment")],
            pr_author="author1",
        )
        assert result["total_comments"] == 0
        assert result["total_reviewers"] == 0

    def test_includes_self_comments_when_flag_set(self):
        result = self._run(
            review_comments=[_make_review_comment("author1", "Self comment")],
            pr_author="author1",
            exclude_self_comments=False,
        )
        assert result["total_comments"] == 1
        assert result["reviewers"][0]["login"] == "author1"

    def test_include_reviewer_filter(self):
        result = self._run(
            review_comments=[
                _make_review_comment("alice"),
                _make_review_comment("bob"),
            ],
            include_reviewers=["alice"],
        )
        assert result["total_reviewers"] == 1
        assert result["reviewers"][0]["login"] == "alice"

    def test_exclude_reviewer_filter(self):
        result = self._run(
            review_comments=[
                _make_review_comment("alice"),
                _make_review_comment("bob"),
            ],
            exclude_reviewers=["bob"],
        )
        assert result["total_reviewers"] == 1
        assert result["reviewers"][0]["login"] == "alice"

    def test_since_filter(self):
        result = self._run(
            review_comments=[
                _make_review_comment("alice", created_at="2025-01-01T00:00:00Z"),
                _make_review_comment("bob", created_at="2025-07-01T00:00:00Z"),
            ],
            since="2025-06-01T00:00:00Z",
        )
        assert result["total_comments"] == 1
        assert result["reviewers"][0]["login"] == "bob"

    def test_until_filter(self):
        result = self._run(
            review_comments=[
                _make_review_comment("alice", created_at="2025-01-01T00:00:00Z"),
                _make_review_comment("bob", created_at="2025-07-01T00:00:00Z"),
            ],
            until="2025-06-01T00:00:00Z",
        )
        assert result["total_comments"] == 1
        assert result["reviewers"][0]["login"] == "alice"

    def test_review_comment_type_only(self):
        result = self._run(
            review_comments=[_make_review_comment("alice")],
            issue_comments=[_make_issue_comment("bob")],
            comment_type="review",
        )
        assert result["total_comments"] == 1
        assert result["reviewers"][0]["login"] == "alice"

    def test_issue_comment_type_only(self):
        result = self._run(
            review_comments=[_make_review_comment("alice")],
            issue_comments=[_make_issue_comment("bob")],
            comment_type="issue",
        )
        assert result["total_comments"] == 1
        assert result["reviewers"][0]["login"] == "bob"

    def test_all_comment_types(self):
        result = self._run(
            review_comments=[_make_review_comment("alice")],
            issue_comments=[_make_issue_comment("alice")],
            comment_type="all",
        )
        assert result["total_comments"] == 2
        assert result["reviewers"][0]["login"] == "alice"
        assert result["reviewers"][0]["review_comments"] == 1
        assert result["reviewers"][0]["issue_comments"] == 1

    def test_tracks_prs_per_reviewer(self):
        pr_view = _completed(stdout=json.dumps({"author": {"login": "author1"}}))
        review_comments_pr1 = [_make_review_comment("alice")]
        review_comments_pr2 = [_make_review_comment("alice")]

        call_count = 0

        def paginated_side_effect(endpoint, **_kw):
            nonlocal call_count
            if "/pulls/" in endpoint and "/comments" in endpoint:
                call_count += 1
                if call_count == 1:
                    return review_comments_pr1
                return review_comments_pr2
            return []

        with patch(
            f"{_MODULE}.subprocess.run",
            return_value=pr_view,
        ), patch(
            f"{_MODULE}.gh_api_paginated",
            side_effect=paginated_side_effect,
        ):
            result = get_pr_comments_by_reviewer("o", "r", [1, 2])

        assert result["prs_processed"] == 2
        assert result["reviewers"][0]["login"] == "alice"
        assert result["reviewers"][0]["total_comments"] == 2
        assert len(result["reviewers"][0]["prs"]) == 2

    def test_empty_login_skipped(self):
        result = self._run(
            review_comments=[_make_review_comment("")],
        )
        assert result["total_comments"] == 0

    def test_sorted_by_comment_count(self):
        result = self._run(
            review_comments=[
                _make_review_comment("bob"),
                _make_review_comment("alice"),
                _make_review_comment("alice"),
                _make_review_comment("alice"),
            ],
        )
        assert result["reviewers"][0]["login"] == "alice"
        assert result["reviewers"][0]["total_comments"] == 3
        assert result["reviewers"][1]["login"] == "bob"
        assert result["reviewers"][1]["total_comments"] == 1
