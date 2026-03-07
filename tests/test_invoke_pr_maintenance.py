"""Tests for invoke_pr_maintenance.py consumer script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch
from scripts.github_core.api import RepoInfo

from scripts.github_core.api import RepoInfo

# ---------------------------------------------------------------------------
# Import the consumer script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None, f"Could not load spec for {name}"
    assert spec.loader is not None, f"Spec for {name} has no loader"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("invoke_pr_maintenance")
main = _mod.main
classify_bot = _mod.classify_bot
has_bot_reviewer = _mod.has_bot_reviewer
has_conflicts = _mod.has_conflicts
has_failing_checks = _mod.has_failing_checks
get_derivative_prs = _mod.get_derivative_prs
get_parents_with_derivatives = _mod.get_parents_with_derivatives
get_open_prs = _mod.get_open_prs
discover_and_classify = _mod.discover_and_classify
PROTECTED_BRANCHES = _mod.PROTECTED_BRANCHES
BOT_CATEGORIES = _mod.BOT_CATEGORIES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pr(
    number: int = 1,
    author: str = "human-user",
    head: str = "feat/test",
    base: str = "main",
    mergeable: str = "MERGEABLE",
    review_decision: str | None = None,
    check_state: str = "SUCCESS",
    check_conclusion: str = "SUCCESS",
) -> dict:
    return {
        "number": number,
        "title": f"PR #{number}",
        "author": {"login": author},
        "headRefName": head,
        "baseRefName": base,
        "mergeable": mergeable,
        "reviewDecision": review_decision,
        "reviewRequests": {"nodes": []},
        "commits": {
            "nodes": [{
                "commit": {
                    "statusCheckRollup": {
                        "state": check_state,
                        "contexts": {
                            "nodes": [{
                                "name": "ci",
                                "conclusion": check_conclusion,
                                "status": "COMPLETED",
                            }]
                        },
                    }
                }
            }]
        },
    }


# ---------------------------------------------------------------------------
# Tests: classify_bot
# ---------------------------------------------------------------------------


class TestClassifyBot:
    def test_human_author(self):
        result = classify_bot("some-human")
        assert result["is_bot"] is False
        assert result["category"] == "human"

    def test_agent_controlled_bot(self):
        result = classify_bot("rjmurillo-bot")
        assert result["is_bot"] is True
        assert result["category"] == "agent-controlled"

    def test_mention_triggered_bot(self):
        result = classify_bot("copilot-swe-agent")
        assert result["is_bot"] is True
        assert result["category"] == "mention-triggered"

    def test_review_bot(self):
        result = classify_bot("coderabbitai[bot]")
        assert result["is_bot"] is True
        assert result["category"] == "review-bot"

    def test_case_insensitive(self):
        result = classify_bot("RJMURILLO-BOT")
        assert result["is_bot"] is True

    def test_prefix_match(self):
        result = classify_bot("copilot-swe-agent-extended")
        assert result["is_bot"] is True


# ---------------------------------------------------------------------------
# Tests: has_bot_reviewer
# ---------------------------------------------------------------------------


class TestHasBotReviewer:
    def test_no_review_requests(self):
        assert has_bot_reviewer(None) is False
        assert has_bot_reviewer({}) is False

    def test_no_agent_controlled_reviewer(self):
        requests = {"nodes": [{"requestedReviewer": {"login": "human"}}]}
        assert has_bot_reviewer(requests) is False

    def test_agent_controlled_reviewer(self):
        requests = {"nodes": [{"requestedReviewer": {"login": "rjmurillo-bot"}}]}
        assert has_bot_reviewer(requests) is True

    def test_review_bot_not_agent_controlled(self):
        requests = {"nodes": [{"requestedReviewer": {"login": "coderabbitai[bot]"}}]}
        assert has_bot_reviewer(requests) is False

    def test_missing_login(self):
        requests = {"nodes": [{"requestedReviewer": {"name": "team"}}]}
        assert has_bot_reviewer(requests) is False


# ---------------------------------------------------------------------------
# Tests: has_conflicts / has_failing_checks
# ---------------------------------------------------------------------------


class TestHasConflicts:
    def test_conflicting(self):
        assert has_conflicts({"mergeable": "CONFLICTING"}) is True

    def test_mergeable(self):
        assert has_conflicts({"mergeable": "MERGEABLE"}) is False

    def test_unknown(self):
        assert has_conflicts({"mergeable": "UNKNOWN"}) is False


class TestHasFailingChecks:
    def test_failure_state(self):
        pr = _make_pr(check_state="FAILURE")
        assert has_failing_checks(pr) is True

    def test_error_state(self):
        pr = _make_pr(check_state="ERROR")
        assert has_failing_checks(pr) is True

    def test_success_state(self):
        pr = _make_pr(check_state="SUCCESS")
        assert has_failing_checks(pr) is False

    def test_no_commits(self):
        assert has_failing_checks({"commits": None}) is False
        assert has_failing_checks({"commits": {"nodes": []}}) is False

    def test_no_rollup(self):
        pr = {"commits": {"nodes": [{"commit": {"statusCheckRollup": None}}]}}
        assert has_failing_checks(pr) is False

    def test_context_level_failure(self):
        pr = _make_pr(check_state="SUCCESS", check_conclusion="FAILURE")
        assert has_failing_checks(pr) is True


# ---------------------------------------------------------------------------
# Tests: get_derivative_prs
# ---------------------------------------------------------------------------


class TestGetDerivativePrs:
    def test_no_derivatives(self):
        prs = [_make_pr(base="main")]
        assert get_derivative_prs(prs) == []

    def test_derivative_detected(self):
        prs = [_make_pr(number=1, base="feat/parent", head="feat/child")]
        result = get_derivative_prs(prs)
        assert len(result) == 1
        assert result[0]["number"] == 1
        assert result[0]["targetBranch"] == "feat/parent"

    def test_protected_branches_excluded(self):
        for branch in PROTECTED_BRANCHES:
            prs = [_make_pr(base=branch)]
            assert get_derivative_prs(prs) == []


# ---------------------------------------------------------------------------
# Tests: get_parents_with_derivatives
# ---------------------------------------------------------------------------


class TestGetParentsWithDerivatives:
    def test_maps_derivative_to_parent(self):
        parent = _make_pr(number=1, head="feat/parent", base="main")
        child = _make_pr(number=2, head="feat/child", base="feat/parent")
        prs = [parent, child]
        derivatives = get_derivative_prs(prs)
        parents = get_parents_with_derivatives(prs, derivatives)
        assert len(parents) == 1
        assert parents[0]["parentPR"] == 1
        assert 2 in parents[0]["derivatives"]

    def test_no_matching_parent(self):
        derivatives = [{"number": 2, "targetBranch": "orphan-branch"}]
        parents = get_parents_with_derivatives([], derivatives)
        assert parents == []


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def _mock_rate_limit_ok(self):
        from scripts.github_core import RateLimitResult

        return RateLimitResult(
            success=True,
            core_remaining=5000,
            resources={},
            summary_markdown="",
        )

    def test_rate_limit_too_low_exits_0(self):
        from scripts.github_core import RateLimitResult

        low_result = RateLimitResult(
            success=False,
            core_remaining=10,
            resources={},
            summary_markdown="",
        )
        with patch(
            "invoke_pr_maintenance.check_workflow_rate_limit",
            return_value=low_result,
        ):
            rc = main(["--owner", "o", "--repo", "r"])
        assert rc == 0

    def test_rate_limit_failure_exits_0(self):
        with patch(
            "invoke_pr_maintenance.check_workflow_rate_limit",
            side_effect=RuntimeError("rate limit check failed"),
        ):
            rc = main(["--owner", "o", "--repo", "r"])
        assert rc == 0

    def test_repo_resolution_failure_exits_2(self):
        with patch(
            "invoke_pr_maintenance.check_workflow_rate_limit",
            return_value=self._mock_rate_limit_ok(),
        ), patch(
            "invoke_pr_maintenance.resolve_repo_params",
            side_effect=Exception("cannot resolve"),
        ):
            rc = main(["--owner", "", "--repo", ""])
        assert rc == 2

    def test_json_output_mode(self):
        with patch(
            "invoke_pr_maintenance.check_workflow_rate_limit",
            return_value=self._mock_rate_limit_ok(),
        ), patch(
            "invoke_pr_maintenance.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "invoke_pr_maintenance.get_open_prs",
            return_value=[],
        ):
            rc = main(["--owner", "o", "--repo", "r", "--output-json"])
        assert rc == 0

    def test_summary_output_mode(self, tmp_path, monkeypatch):
        summary_file = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
        with patch(
            "invoke_pr_maintenance.check_workflow_rate_limit",
            return_value=self._mock_rate_limit_ok(),
        ), patch(
            "invoke_pr_maintenance.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "invoke_pr_maintenance.get_open_prs",
            return_value=[],
        ):
            rc = main(["--owner", "o", "--repo", "r"])
        assert rc == 0
        assert summary_file.exists()
        content = summary_file.read_text()
        assert "PR Discovery Summary" in content
