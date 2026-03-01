"""Tests for get_unaddressed_comments.py skill script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from scripts.github_core.api import RepoInfo

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


_mod = _import_script("get_unaddressed_comments")
main = _mod.main
build_parser = _mod.build_parser
get_lifecycle_state = _mod.get_lifecycle_state
comment_needs_action = _mod.comment_needs_action
classify_domain = _mod.classify_domain
get_discussion_sub_state = _mod.get_discussion_sub_state


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

    def test_bot_only_default_true(self):
        args = build_parser().parse_args(["--pull-request", "1"])
        assert args.bot_only is True

    def test_no_bot_only(self):
        args = build_parser().parse_args(["--pull-request", "1", "--no-bot-only"])
        assert args.bot_only is False


# ---------------------------------------------------------------------------
# Tests: get_lifecycle_state
# ---------------------------------------------------------------------------


class TestGetLifecycleState:
    def test_resolved(self):
        assert get_lifecycle_state(0, 0, True) == "RESOLVED"

    def test_new(self):
        assert get_lifecycle_state(0, 0, False) == "NEW"

    def test_acknowledged(self):
        assert get_lifecycle_state(1, 0, False) == "ACKNOWLEDGED"

    def test_in_discussion(self):
        assert get_lifecycle_state(1, 1, False) == "IN_DISCUSSION"


# ---------------------------------------------------------------------------
# Tests: comment_needs_action
# ---------------------------------------------------------------------------


class TestCommentNeedsAction:
    def test_resolved_no_action(self):
        assert comment_needs_action("RESOLVED", None) is False

    def test_new_needs_action(self):
        assert comment_needs_action("NEW", None) is True

    def test_acknowledged_needs_action(self):
        assert comment_needs_action("ACKNOWLEDGED", None) is True

    def test_in_discussion_wontfix_no_action(self):
        assert comment_needs_action("IN_DISCUSSION", "WONT_FIX") is False

    def test_in_discussion_fix_committed_no_action(self):
        assert comment_needs_action("IN_DISCUSSION", "FIX_COMMITTED") is False

    def test_in_discussion_needs_clarification(self):
        assert comment_needs_action("IN_DISCUSSION", "NEEDS_CLARIFICATION") is True


# ---------------------------------------------------------------------------
# Tests: classify_domain
# ---------------------------------------------------------------------------


class TestClassifyDomain:
    def test_security(self):
        assert classify_domain("CWE-22 vulnerability found") == "security"

    def test_bug(self):
        assert classify_domain("This throws error when empty") == "bug"

    def test_style(self):
        assert classify_domain("Fix the formatting and indentation") == "style"

    def test_summary(self):
        assert classify_domain("## Summary\nOverview of changes") == "summary"

    def test_general(self):
        assert classify_domain("This looks good to me") == "general"

    def test_renaming_is_style(self):
        assert classify_domain("Consider renaming this variable") == "style"

    def test_empty(self):
        assert classify_domain("") == "general"


# ---------------------------------------------------------------------------
# Tests: get_discussion_sub_state
# ---------------------------------------------------------------------------


class TestGetDiscussionSubState:
    def test_empty_replies(self):
        assert get_discussion_sub_state([]) is None

    def test_wontfix(self):
        assert get_discussion_sub_state(["This is out of scope"]) == "WONT_FIX"

    def test_fix_committed(self):
        assert get_discussion_sub_state(["Fixed in commit abc1234"]) == "FIX_COMMITTED"

    def test_fix_described(self):
        assert get_discussion_sub_state(["Updated the implementation"]) == "FIX_DESCRIBED"

    def test_needs_clarification(self):
        assert get_discussion_sub_state(["Can you clarify?"]) == "NEEDS_CLARIFICATION"


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "get_unaddressed_comments.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_no_comments(self, capsys):
        with patch(
            "get_unaddressed_comments.assert_gh_authenticated",
        ), patch(
            "get_unaddressed_comments.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_unaddressed_comments.gh_api_paginated",
            return_value=[],
        ), patch(
            "get_unaddressed_comments.get_unresolved_review_threads",
            return_value=[],
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["TotalCount"] == 0

    def test_bot_comment_new_state(self, capsys):
        raw_comments = [
            {
                "id": 100,
                "user": {"login": "coderabbit[bot]", "type": "Bot"},
                "body": "Consider refactoring this",
                "path": "src/main.py",
                "line": 10,
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
            "get_unaddressed_comments.assert_gh_authenticated",
        ), patch(
            "get_unaddressed_comments.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_unaddressed_comments.gh_api_paginated",
            return_value=raw_comments,
        ), patch(
            "get_unaddressed_comments.get_unresolved_review_threads",
            return_value=unresolved_threads,
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["TotalCount"] == 1
        assert output["Comments"][0]["LifecycleState"] == "NEW"
