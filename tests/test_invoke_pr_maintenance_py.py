"""Tests for invoke_pr_maintenance.py PR discovery and classification."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from scripts.invoke_pr_maintenance import (
    classify_prs,
    get_bot_author_info,
    get_open_prs,
    has_failing_checks,
    is_bot_reviewer,
    main,
)


class TestGetBotAuthorInfo:
    def test_detects_agent_controlled_bot(self) -> None:
        info = get_bot_author_info("rjmurillo-bot")
        assert info.is_bot is True
        assert info.category == "agent-controlled"

    def test_detects_mention_triggered_bot(self) -> None:
        info = get_bot_author_info("copilot-swe-agent")
        assert info.is_bot is True
        assert info.category == "mention-triggered"

    def test_detects_review_bot(self) -> None:
        info = get_bot_author_info("coderabbitai")
        assert info.is_bot is True
        assert info.category == "review-bot"

    def test_identifies_human(self) -> None:
        info = get_bot_author_info("regularuser")
        assert info.is_bot is False
        assert info.category == "human"

    def test_case_insensitive_matching(self) -> None:
        info = get_bot_author_info("RjMurillo-Bot")
        assert info.is_bot is True


class TestIsBotReviewer:
    def test_returns_true_for_agent_reviewer(self) -> None:
        review_requests = {
            "nodes": [{"requestedReviewer": {"login": "rjmurillo-bot"}}]
        }
        assert is_bot_reviewer(review_requests) is True

    def test_returns_false_for_human_reviewer(self) -> None:
        review_requests = {
            "nodes": [{"requestedReviewer": {"login": "humandev"}}]
        }
        assert is_bot_reviewer(review_requests) is False

    def test_returns_false_for_none(self) -> None:
        assert is_bot_reviewer(None) is False

    def test_returns_false_for_empty_nodes(self) -> None:
        assert is_bot_reviewer({"nodes": []}) is False


class TestHasFailingChecks:
    def test_returns_true_for_failure_state(self) -> None:
        rollup = {"state": "FAILURE", "contexts": {"nodes": []}}
        pr = {
            "commits": {
                "nodes": [
                    {"commit": {"statusCheckRollup": rollup}}
                ]
            }
        }
        assert has_failing_checks(pr) is True

    def test_returns_false_for_success_state(self) -> None:
        rollup = {"state": "SUCCESS", "contexts": {"nodes": []}}
        pr = {
            "commits": {
                "nodes": [
                    {"commit": {"statusCheckRollup": rollup}}
                ]
            }
        }
        assert has_failing_checks(pr) is False

    def test_returns_false_when_no_commits(self) -> None:
        assert has_failing_checks({"commits": {"nodes": []}}) is False

    def test_returns_false_when_no_rollup(self) -> None:
        pr = {"commits": {"nodes": [{"commit": {"statusCheckRollup": None}}]}}
        assert has_failing_checks(pr) is False

    def test_returns_true_for_context_failure(self) -> None:
        pr = {
            "commits": {
                "nodes": [
                    {
                        "commit": {
                            "statusCheckRollup": {
                                "state": "PENDING",
                                "contexts": {
                                    "nodes": [{"conclusion": "FAILURE"}]
                                },
                            }
                        }
                    }
                ]
            }
        }
        assert has_failing_checks(pr) is True


class TestClassifyPrs:
    def test_detects_derivative_prs(self) -> None:
        prs = [
            {
                "number": 1,
                "title": "Parent PR",
                "author": {"login": "user"},
                "headRefName": "feat/parent",
                "baseRefName": "main",
                "mergeable": "MERGEABLE",
                "reviewDecision": None,
                "reviewRequests": {"nodes": []},
                "commits": {"nodes": []},
            },
            {
                "number": 2,
                "title": "Child PR",
                "author": {"login": "user"},
                "headRefName": "feat/child",
                "baseRefName": "feat/parent",
                "mergeable": "MERGEABLE",
                "reviewDecision": None,
                "reviewRequests": {"nodes": []},
                "commits": {"nodes": []},
            },
        ]
        results = classify_prs("owner", "repo", prs)
        assert len(results.derivative_prs) == 1
        assert results.derivative_prs[0]["number"] == 2

    def test_classifies_agent_pr_with_changes_requested(self) -> None:
        prs = [
            {
                "number": 10,
                "title": "Bot PR",
                "author": {"login": "rjmurillo-bot"},
                "headRefName": "feat/auto",
                "baseRefName": "main",
                "mergeable": "MERGEABLE",
                "reviewDecision": "CHANGES_REQUESTED",
                "reviewRequests": {"nodes": []},
                "commits": {"nodes": []},
            },
        ]
        results = classify_prs("owner", "repo", prs)
        assert len(results.action_required) == 1
        assert results.action_required[0]["reason"] == "CHANGES_REQUESTED"
        assert results.action_required[0]["category"] == "agent-controlled"


class TestGetOpenPrs:
    def test_raises_on_api_failure(self) -> None:
        failed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="API error"
        )
        with patch("scripts.invoke_pr_maintenance.run_gh", return_value=failed):
            with pytest.raises(RuntimeError, match="Failed to query PRs"):
                get_open_prs("owner", "repo", 20)

    def test_raises_on_invalid_json(self) -> None:
        bad_json = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="not json", stderr=""
        )
        with patch("scripts.invoke_pr_maintenance.run_gh", return_value=bad_json):
            with pytest.raises(RuntimeError, match="Failed to parse PR response"):
                get_open_prs("owner", "repo", 20)

    def test_raises_on_missing_keys(self) -> None:
        incomplete = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"data": {}}', stderr=""
        )
        with patch("scripts.invoke_pr_maintenance.run_gh", return_value=incomplete):
            with pytest.raises(RuntimeError, match="Failed to parse PR response"):
                get_open_prs("owner", "repo", 20)

    def test_returns_prs_on_success(self) -> None:
        valid = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"data":{"repository":{"pullRequests":{"nodes":[{"number":1}]}}}}',
            stderr="",
        )
        with patch("scripts.invoke_pr_maintenance.run_gh", return_value=valid):
            result = get_open_prs("owner", "repo", 20)
        assert result == [{"number": 1}]


class TestClassifyPrsErrors:
    def test_raises_on_key_error_in_pr(self) -> None:
        prs = [
            {
                "baseRefName": "main",
                "headRefName": "feat/test",
                "author": {"login": "rjmurillo-bot"},
                "mergeable": "MERGEABLE",
                "reviewDecision": "CHANGES_REQUESTED",
                "reviewRequests": {"nodes": []},
                "commits": {"nodes": []},
            },
        ]
        with pytest.raises(RuntimeError, match=r"Classification failed.*missing"):
            classify_prs("owner", "repo", prs)

    def test_non_key_error_propagates_directly(self) -> None:
        prs = [
            {
                "number": 1,
                "title": "Test",
                "baseRefName": "main",
                "headRefName": "feat/test",
                "author": {"login": "rjmurillo-bot"},
                "mergeable": "MERGEABLE",
                "reviewDecision": "CHANGES_REQUESTED",
                "reviewRequests": {"nodes": []},
                "commits": {"nodes": []},
            },
        ]
        with patch(
            "scripts.invoke_pr_maintenance.get_bot_author_info",
            side_effect=TypeError("unexpected type"),
        ):
            with pytest.raises(TypeError, match="unexpected type"):
                classify_prs("owner", "repo", prs)


class TestMain:
    @patch("scripts.invoke_pr_maintenance.check_rate_limit", return_value=False)
    def test_exits_0_on_low_rate_limit(self, _mock: MagicMock) -> None:
        assert main([]) == 0

    @patch("scripts.invoke_pr_maintenance.get_open_prs", return_value=[])
    @patch("scripts.invoke_pr_maintenance.get_repo_info", return_value=("owner", "repo"))
    @patch("scripts.invoke_pr_maintenance.check_rate_limit", return_value=True)
    def test_output_json_mode(self, _rate: MagicMock, _repo: MagicMock, _prs: MagicMock) -> None:
        result = main(["--output-json"])
        assert result == 0

    @patch(
        "scripts.invoke_pr_maintenance.get_open_prs",
        side_effect=RuntimeError("API error"),
    )
    @patch("scripts.invoke_pr_maintenance.get_repo_info", return_value=("owner", "repo"))
    @patch("scripts.invoke_pr_maintenance.check_rate_limit", return_value=True)
    def test_exits_2_on_api_failure(
        self, _rate: MagicMock, _repo: MagicMock, _prs: MagicMock
    ) -> None:
        result = main(["--output-json"])
        assert result == 2
