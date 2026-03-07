"""Tests for invoke_pr_maintenance.py PR discovery and classification."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from scripts.github_core.api import RepoInfo

from scripts.github_core.api import RepoInfo
from scripts.invoke_pr_maintenance import (
    classify_prs,
    get_bot_author_info,
    get_open_prs,
    has_failing_checks,
    has_unresolved_threads,
    is_bot_reviewer,
    main,
    run_gh,
)


class TestRunGhTimeout:
    @patch("scripts.invoke_pr_maintenance.subprocess.run")
    def test_passes_timeout_60(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        run_gh("api", "rate_limit")
        mock_run.assert_called_once_with(
            ["gh", "api", "rate_limit"],
            capture_output=True,
            text=True,
            timeout=60,
        )

    @patch("scripts.invoke_pr_maintenance.subprocess.run")
    def test_timeout_raises_timeout_expired(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["gh"], timeout=60)
        with pytest.raises(subprocess.TimeoutExpired):
            run_gh("api", "rate_limit")


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


class TestHasUnresolvedThreads:
    def test_returns_true_when_threads_unresolved(self) -> None:
        pr = {
            "reviewThreads": {
                "nodes": [
                    {"isResolved": False},
                    {"isResolved": True},
                ]
            }
        }
        assert has_unresolved_threads(pr) is True

    def test_returns_false_when_all_resolved(self) -> None:
        pr = {
            "reviewThreads": {
                "nodes": [
                    {"isResolved": True},
                    {"isResolved": True},
                ]
            }
        }
        assert has_unresolved_threads(pr) is False

    def test_returns_false_when_no_threads(self) -> None:
        pr = {"reviewThreads": {"nodes": []}}
        assert has_unresolved_threads(pr) is False

    def test_returns_false_when_missing_key(self) -> None:
        assert has_unresolved_threads({}) is False

    def test_returns_false_when_threads_none(self) -> None:
        assert has_unresolved_threads({"reviewThreads": None}) is False


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

    def test_classifies_pr_with_unresolved_threads(self) -> None:
        prs = [
            {
                "number": 42,
                "title": "PR with unresolved threads",
                "author": {"login": "rjmurillo-bot"},
                "headRefName": "feat/fix",
                "baseRefName": "main",
                "mergeable": "MERGEABLE",
                "reviewDecision": None,
                "reviewRequests": {"nodes": []},
                "reviewThreads": {
                    "nodes": [
                        {"isResolved": False},
                        {"isResolved": True},
                    ]
                },
                "commits": {"nodes": []},
            },
        ]
        results = classify_prs("owner", "repo", prs)
        assert len(results.action_required) == 1
        assert results.action_required[0]["reason"] == "HAS_UNRESOLVED_THREADS"
        assert results.action_required[0]["category"] == "agent-controlled"

    def test_skips_pr_with_all_threads_resolved(self) -> None:
        prs = [
            {
                "number": 43,
                "title": "PR with all threads resolved",
                "author": {"login": "rjmurillo-bot"},
                "headRefName": "feat/done",
                "baseRefName": "main",
                "mergeable": "MERGEABLE",
                "reviewDecision": None,
                "reviewRequests": {"nodes": []},
                "reviewThreads": {
                    "nodes": [
                        {"isResolved": True},
                    ]
                },
                "commits": {"nodes": []},
            },
        ]
        results = classify_prs("owner", "repo", prs)
        assert len(results.action_required) == 0

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
    def _rate_limit_ok(self) -> object:
        from scripts.github_core import RateLimitResult

        return RateLimitResult(
            success=True,
            core_remaining=5000,
            resources={},
            summary_markdown="",
        )

    def _rate_limit_low(self) -> object:
        from scripts.github_core import RateLimitResult

        return RateLimitResult(
            success=False,
            core_remaining=10,
            resources={},
            summary_markdown="",
        )

    @patch(
        "scripts.invoke_pr_maintenance.check_workflow_rate_limit",
    )
    def test_exits_0_on_low_rate_limit(self, mock_rate: MagicMock) -> None:
        mock_rate.return_value = self._rate_limit_low()
        assert main([]) == 0

    @patch(
        "scripts.invoke_pr_maintenance.check_workflow_rate_limit",
        side_effect=RuntimeError("gh: command not found"),
    )
    def test_exits_0_on_rate_limit_check_failure(self, _mock: MagicMock) -> None:
        assert main([]) == 0

    @patch("scripts.invoke_pr_maintenance.get_open_prs", return_value=[])
    @patch(
        "scripts.invoke_pr_maintenance.resolve_repo_params",
        return_value=RepoInfo(owner="owner", repo="repo"),
    )
    @patch("scripts.invoke_pr_maintenance.check_workflow_rate_limit")
    def test_output_json_mode(
        self, mock_rate: MagicMock, _repo: MagicMock, _prs: MagicMock
    ) -> None:
        mock_rate.return_value = self._rate_limit_ok()
        result = main(["--output-json"])
        assert result == 0

    @patch(
        "scripts.invoke_pr_maintenance.get_open_prs",
        side_effect=RuntimeError("API error"),
    )
    @patch(
        "scripts.invoke_pr_maintenance.resolve_repo_params",
        return_value=RepoInfo(owner="owner", repo="repo"),
    )
    @patch("scripts.invoke_pr_maintenance.check_workflow_rate_limit")
    def test_exits_2_on_api_failure(
        self, mock_rate: MagicMock, _repo: MagicMock, _prs: MagicMock
    ) -> None:
        mock_rate.return_value = self._rate_limit_ok()
        result = main(["--output-json"])
        assert result == 2

    @patch(
        "scripts.invoke_pr_maintenance.resolve_repo_params",
        side_effect=RuntimeError("cannot resolve"),
    )
    @patch("scripts.invoke_pr_maintenance.check_workflow_rate_limit")
    def test_exits_2_on_repo_resolution_failure(
        self, mock_rate: MagicMock, _repo: MagicMock
    ) -> None:
        mock_rate.return_value = self._rate_limit_ok()
        result = main(["--owner", "", "--repo", ""])
        assert result == 2


class TestHasUnresolvedThreads:
    """Tests for has_unresolved_threads function (Issue #974)."""

    def test_returns_true_when_threads_exist(self) -> None:
        from scripts.invoke_pr_maintenance import has_unresolved_threads

        pr = {
            "reviewThreads": {
                "nodes": [{"isResolved": False}],
            }
        }
        assert has_unresolved_threads(pr) is True

    def test_returns_false_when_no_threads(self) -> None:
        from scripts.invoke_pr_maintenance import has_unresolved_threads

        pr = {"reviewThreads": {"nodes": []}}
        assert has_unresolved_threads(pr) is False

    def test_warns_when_threads_truncated(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        from scripts.invoke_pr_maintenance import has_unresolved_threads

        pr = {
            "number": 42,
            "reviewThreads": {
                "totalCount": 150,
                "nodes": [{"isResolved": True}] * 100,
            },
        }
        with caplog.at_level(logging.WARNING):
            has_unresolved_threads(pr)
        assert "150 review threads but only 100 fetched" in caplog.text


class TestClassifyPrsWithUnresolvedThreads:
    """Tests for classify_prs with unresolved thread detection (Issue #974)."""

    def test_detects_unresolved_threads_for_agent_pr(self) -> None:
        """PR with acknowledged (eyes) but unresolved threads needs action."""
        prs = [
            {
                "number": 100,
                "title": "Agent PR with unresolved threads",
                "author": {"login": "rjmurillo-bot"},
                "headRefName": "feat/test",
                "baseRefName": "main",
                "mergeable": "MERGEABLE",
                "reviewDecision": None,
                "reviewRequests": {"nodes": []},
                "reviewThreads": {"nodes": [{"isResolved": False}]},
                "commits": {"nodes": []},
            },
        ]
        results = classify_prs("owner", "repo", prs)

        assert len(results.action_required) == 1
        assert results.action_required[0]["reason"] == "HAS_UNRESOLVED_THREADS"
        assert results.action_required[0]["hasUnresolvedThreads"] is True

    def test_human_pr_with_unresolved_threads_classified_as_blocked(self) -> None:
        """Human PRs with unresolved threads are classified as blocked."""
        prs = [
            {
                "number": 200,
                "title": "Human PR",
                "author": {"login": "humandev"},
                "headRefName": "feat/human",
                "baseRefName": "main",
                "mergeable": "MERGEABLE",
                "reviewDecision": None,
                "reviewRequests": {"nodes": []},
                "reviewThreads": {"nodes": [{"isResolved": False}]},
                "commits": {"nodes": []},
            },
        ]
        results = classify_prs("owner", "repo", prs)

        assert len(results.blocked) == 1
        assert results.blocked[0]["reason"] == "HAS_UNRESOLVED_THREADS"

    def test_reason_priority_conflicts_over_threads(self) -> None:
        """Conflicts take priority over unresolved threads in reason."""
        prs = [
            {
                "number": 300,
                "title": "Agent PR with conflicts and threads",
                "author": {"login": "rjmurillo-bot"},
                "headRefName": "feat/conflict",
                "baseRefName": "main",
                "mergeable": "CONFLICTING",
                "reviewDecision": None,
                "reviewRequests": {"nodes": []},
                "reviewThreads": {"nodes": [{"isResolved": False}]},
                "commits": {"nodes": []},
            },
        ]
        results = classify_prs("owner", "repo", prs)

        assert results.action_required[0]["reason"] == "HAS_CONFLICTS"
        assert results.action_required[0]["hasConflicts"] is True
        assert results.action_required[0]["hasUnresolvedThreads"] is True
