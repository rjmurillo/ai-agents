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
classify_reviewer_priority = _mod.classify_reviewer_priority


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _review_comment(
    cid: int, login: str, body: str, ctype: str = "Bot", created: str = "2024-01-01"
):
    return {
        "id": cid,
        "user": {"login": login, "type": ctype},
        "body": body,
        "path": "src/main.py",
        "line": 10,
        "original_line": 10,
        "reactions": {"eyes": 0},
        "in_reply_to_id": None,
        "created_at": created,
        "updated_at": created,
        "html_url": "https://example.com",
    }


def _issue_comment(
    cid: int, login: str, body: str, ctype: str = "User", created: str = "2024-01-01"
):
    return {
        "id": cid,
        "user": {"login": login, "type": ctype},
        "body": body,
        "reactions": {"eyes": 0},
        "created_at": created,
        "updated_at": created,
        "html_url": "https://example.com",
    }


def _run_main(argv, review=None, issue=None, unresolved=None):
    """Run main() with GitHub I/O mocked at the boundary.

    gh_api_paginated is called once (review comments) or, when the argv includes
    --include-issue-comments, twice (review then issue). Pass issue=[...] to
    exercise the second call. The real is_bot / classify_domain collaborators
    run unmocked so classification stays faithful.
    """
    side = [review or []]
    if issue is not None:
        side.append(issue)
    with patch(
        "get_pr_review_comments.assert_gh_authenticated",
    ), patch(
        "get_pr_review_comments.resolve_repo_params",
        return_value=RepoInfo(owner="o", repo="r"),
    ), patch(
        "get_pr_review_comments.gh_api_paginated",
        side_effect=side,
    ), patch(
        "get_pr_review_comments.get_unresolved_review_threads",
        return_value=unresolved or [],
    ):
        return main(argv)


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

    def test_group_by_reviewer_priority_defaults_false(self):
        args = build_parser().parse_args(["--pull-request", "1"])
        assert args.group_by_reviewer_priority is False

    def test_group_by_reviewer_priority_parses(self):
        args = build_parser().parse_args(
            ["--pull-request", "1", "--group-by-reviewer-priority"]
        )
        assert args.group_by_reviewer_priority is True

    def test_help_text_lists_reviewer_priority_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["--help"])

        assert exc.value.code == 0
        help_text = capsys.readouterr().out
        assert "--group-by-reviewer-priority" in help_text
        assert "P2 CodeRabbit/Copilot, then Unknown" in help_text


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

    def test_review_comment_with_null_user_uses_empty_author(self, capsys):
        review = _review_comment(100, "unused", "Deleted account comment")
        review["user"] = None

        rc = _run_main(["--pull-request", "42"], review=[review])

        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Comments"][0]["Author"] == ""
        assert output["Comments"][0]["AuthorType"] == ""

    def test_issue_comment_with_null_user_uses_empty_author(self, capsys):
        issue = _issue_comment(200, "unused", "Deleted account comment")
        issue["user"] = None

        rc = _run_main(
            ["--pull-request", "42", "--include-issue-comments"],
            review=[],
            issue=[issue],
        )

        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Comments"][0]["Author"] == ""
        assert output["Comments"][0]["AuthorType"] == ""

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


# ---------------------------------------------------------------------------
# Tests: classify_reviewer_priority (unit)
# ---------------------------------------------------------------------------


class TestClassifyReviewerPriority:
    def test_cursor_bot_is_p0(self):
        assert classify_reviewer_priority("cursor[bot]", "Bot") == "P0"

    def test_cursor_bot_case_insensitive(self):
        assert classify_reviewer_priority("Cursor[Bot]", "Bot") == "P0"

    def test_human_reviewer_is_p1(self):
        assert classify_reviewer_priority("alice", "User") == "P1"

    def test_coderabbit_is_p2(self):
        assert classify_reviewer_priority("coderabbitai[bot]", "Bot") == "P2"

    def test_copilot_is_p2(self):
        assert classify_reviewer_priority("Copilot", "Bot") == "P2"

    def test_copilot_bot_login_variant_is_p2(self):
        assert classify_reviewer_priority("github-copilot[bot]", "Bot") == "P2"

    def test_unrecognized_bot_is_unknown(self):
        assert classify_reviewer_priority("randobot[bot]", "Bot") == "Unknown"

    def test_bot_by_type_only_is_unknown(self):
        assert classify_reviewer_priority("mystery", "Bot") == "Unknown"


# ---------------------------------------------------------------------------
# Tests: --group-by-reviewer-priority output mode
# ---------------------------------------------------------------------------


class TestGroupByReviewerPriority:
    def test_documented_command_groups_reviewer_then_domain(self, capsys):
        """The exact command copied from pr-comment-responder SKILL.md runs and
        nests reviewer priority outside, domain inside."""
        review = [
            _review_comment(1, "cursor[bot]", "Potential SQL injection vulnerability"),
            _review_comment(2, "human-dev", "This will crash with an exception", ctype="User"),
            _review_comment(3, "coderabbitai[bot]", "Fix the naming convention"),
            _review_comment(4, "randobot[bot]", "Just a passing note"),
        ]
        issue = [
            _issue_comment(5, "human-dev", "Please add authentication here", ctype="User"),
        ]
        rc = _run_main(
            [
                "--pull-request", "3076",
                "--group-by-reviewer-priority",
                "--group-by-domain",
                "--include-issue-comments",
            ],
            review=review,
            issue=issue,
        )
        assert rc == 0
        out = json.loads(capsys.readouterr().out)

        assert out["P0"]["Security"][0]["Author"] == "cursor[bot]"
        assert out["P1"]["Bug"][0]["Author"] == "human-dev"
        assert out["P2"]["Style"][0]["Author"] == "coderabbitai[bot]"
        assert out["Unknown"]["General"][0]["Author"] == "randobot[bot]"
        # Human security comment stays in the human tier; it never jumps to P0/P2.
        assert out["P1"]["Security"][0]["Author"] == "human-dev"
        assert out["TotalComments"] == 5
        assert out["ReviewerPriorityCounts"] == {"P0": 1, "P1": 2, "P2": 1, "Unknown": 1}

    def test_tier_key_order_is_p0_p1_p2_unknown(self, capsys):
        review = [_review_comment(1, "cursor[bot]", "SQL injection")]
        rc = _run_main(["--pull-request", "1", "--group-by-reviewer-priority"], review=review)
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert list(out.keys())[:4] == ["P0", "P1", "P2", "Unknown"]

    def test_domain_key_order_within_tier(self, capsys):
        review = [_review_comment(1, "cursor[bot]", "SQL injection")]
        rc = _run_main(
            ["--pull-request", "1", "--group-by-reviewer-priority", "--group-by-domain"],
            review=review,
        )
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert list(out["P0"].keys()) == ["Security", "Bug", "Style", "Summary", "General"]

    def test_flat_lists_without_domain(self, capsys):
        review = [
            _review_comment(1, "cursor[bot]", "note a"),
            _review_comment(2, "human-dev", "note b", ctype="User"),
        ]
        rc = _run_main(["--pull-request", "1", "--group-by-reviewer-priority"], review=review)
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert isinstance(out["P0"], list)
        assert out["P0"][0]["Author"] == "cursor[bot]"
        assert out["P1"][0]["Author"] == "human-dev"
        assert out["P2"] == []

    def test_unknown_reviewer_bucket(self, capsys):
        review = [_review_comment(1, "randobot[bot]", "Just a passing note")]
        rc = _run_main(["--pull-request", "1", "--group-by-reviewer-priority"], review=review)
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["Unknown"][0]["Author"] == "randobot[bot]"
        assert out["ReviewerPriorityCounts"]["Unknown"] == 1
        assert out["P0"] == []

    def test_pagination_places_every_comment(self, capsys):
        review = [
            _review_comment(1, "cursor[bot]", "SQL injection", created="2024-01-01"),
            _review_comment(2, "human-dev", "crash", ctype="User", created="2024-01-02"),
            _review_comment(3, "coderabbitai[bot]", "refactor naming", created="2024-01-03"),
            _review_comment(4, "randobot[bot]", "note", created="2024-01-04"),
            _review_comment(5, "human-two", "another crash", ctype="User", created="2024-01-05"),
        ]
        rc = _run_main(["--pull-request", "1", "--group-by-reviewer-priority"], review=review)
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        counts = out["ReviewerPriorityCounts"]
        assert counts["P0"] + counts["P1"] + counts["P2"] + counts["Unknown"] == 5
        assert counts == {"P0": 1, "P1": 2, "P2": 1, "Unknown": 1}

    def test_no_comments_yields_empty_tiers(self, capsys):
        rc = _run_main(["--pull-request", "1", "--group-by-reviewer-priority"], review=[])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["TotalComments"] == 0
        assert out["P0"] == [] and out["P1"] == [] and out["P2"] == [] and out["Unknown"] == []


class TestGroupByDomainRegression:
    def test_domain_alone_keeps_flat_domain_structure(self, capsys):
        """--group-by-domain without the reviewer flag still returns the flat
        Security/Bug/Style/Summary/General structure (no reviewer tiers)."""
        review = [_review_comment(1, "cursor[bot]", "SQL injection")]
        rc = _run_main(["--pull-request", "1", "--group-by-domain"], review=review)
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert "P0" not in out
        assert out["Security"][0]["Author"] == "cursor[bot]"
        assert list(out.keys())[:5] == ["Security", "Bug", "Style", "Summary", "General"]
