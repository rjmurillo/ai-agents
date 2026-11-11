"""Fetch, CLI and workflow tests for scripts/agent_pr_intervention_metrics.py."""

from __future__ import annotations

import subprocess
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from scripts import agent_pr_intervention_metrics as m
from scripts import update_reviewer_signal_stats as stats_script
from scripts.github_core.api import RateLimitStatus
from tests.agent_pr_intervention_helpers import (
    BOT,
    HUMAN,
    NOW,
    OWNER_NAME,
    _page,
    _pr,
    _thread,
)

# ---------------------------------------------------------------------------
# Lossless fetching
# ---------------------------------------------------------------------------


class TestWriteReportFailure:
    def test_failed_replace_leaves_no_temp_file(self, tmp_path: Path) -> None:
        target = tmp_path / "report.md"
        with (
            patch("scripts.agent_pr_intervention_metrics.os.replace", side_effect=OSError("disk")),
            pytest.raises(OSError),
        ):
            m.write_report(target, "hello")
        assert list(tmp_path.iterdir()) == []


class TestFetch:
    SINCE = NOW - timedelta(days=30)

    def test_pages_until_no_next_page(self) -> None:
        pages = [_page([_pr(2)], True, "c1"), _page([_pr(1)], False, None)]
        with patch.object(m, "gh_graphql", side_effect=pages) as gql:
            result = m.fetch_prs_created_since(OWNER_NAME, "r", self.SINCE)
        assert [p["number"] for p in result] == [2, 1]
        assert gql.call_args_list[1].args[1]["cursor"] == "c1"

    def test_stops_at_first_pr_older_than_window(self) -> None:
        pages = [_page([_pr(2), _pr(1, days_old=40)], True), _page([_pr(0)], False)]
        with patch.object(m, "gh_graphql", side_effect=pages) as gql:
            result = m.fetch_prs_created_since(OWNER_NAME, "r", self.SINCE)
        assert [p["number"] for p in result] == [2]
        assert gql.call_count == 1

    def test_missing_cursor_raises(self) -> None:
        with (
            patch.object(m, "gh_graphql", return_value=_page([_pr(1)], True, None)),
            pytest.raises(RuntimeError, match="no cursor"),
        ):
            m.fetch_prs_created_since(OWNER_NAME, "r", self.SINCE)

    def test_page_cap_raises_instead_of_warning(self) -> None:
        with (
            patch.object(m, "MAX_PR_PAGES", 2),
            patch.object(m, "gh_graphql", side_effect=lambda *_: _page([_pr(1)], True)),
            pytest.raises(RuntimeError, match="exceeded 2 pages"),
        ):
            m.fetch_prs_created_since(OWNER_NAME, "r", self.SINCE)

    def test_null_repository_raises(self) -> None:
        with (
            patch.object(m, "gh_graphql", return_value={"repository": None}),
            pytest.raises(RuntimeError, match="Could not read"),
        ):
            m.fetch_prs_created_since(OWNER_NAME, "r", self.SINCE)

    def test_overflowing_thread_list_is_paged_to_completion(self) -> None:
        pr = _pr(7)
        pr["reviewThreads"] = {
            "nodes": [_thread(BOT)],
            "pageInfo": {"hasNextPage": True, "endCursor": "t1"},
        }
        follow_up = {
            "node": {
                "reviewThreads": {
                    "nodes": [_thread(HUMAN)],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }
        with patch.object(m, "gh_graphql", side_effect=[_page([pr], False), follow_up]) as gql:
            result = m.fetch_prs_created_since(OWNER_NAME, "r", self.SINCE)
        assert m.count_interventions(result[0]) == 1
        assert gql.call_args_list[1].args[1] == {"id": "PR_7", "cursor": "t1"}

    def test_overflowing_list_without_cursor_raises(self) -> None:
        pr = _pr(7)
        pr["reviews"] = {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": None}}
        with (
            patch.object(m, "gh_graphql", return_value=_page([pr], False)),
            pytest.raises(RuntimeError, match="no cursor"),
        ):
            m.fetch_prs_created_since(OWNER_NAME, "r", self.SINCE)

    def test_null_follow_up_node_raises(self) -> None:
        pr = _pr(7)
        pr["reviews"] = {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "r1"}}
        with (
            patch.object(m, "gh_graphql", side_effect=[_page([pr], False), {"node": None}]),
            pytest.raises(RuntimeError, match="unreadable"),
        ):
            m.fetch_prs_created_since(OWNER_NAME, "r", self.SINCE)

    def test_follow_up_page_without_page_info_raises(self) -> None:
        pr = _pr(7)
        pr["reviews"] = {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "r1"}}
        follow_up: dict[str, Any] = {"node": {"reviews": {"nodes": []}}}
        with (
            patch.object(m, "gh_graphql", side_effect=[_page([pr], False), follow_up]),
            pytest.raises(RuntimeError, match="unreadable"),
        ):
            m.fetch_prs_created_since(OWNER_NAME, "r", self.SINCE)

    def test_first_page_without_page_info_raises(self) -> None:
        pr = _pr(7)
        del pr["reviewThreads"]["pageInfo"]
        with (
            patch.object(m, "gh_graphql", return_value=_page([pr], False)),
            pytest.raises(RuntimeError, match="no pageInfo"),
        ):
            m.fetch_prs_created_since(OWNER_NAME, "r", self.SINCE)

    def test_human_pr_is_dropped_without_follow_up_paging(self) -> None:
        human = _pr(5, body="Plain.", author=HUMAN)
        human["reviews"] = {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "x"}}
        with patch.object(m, "gh_graphql", return_value=_page([human, _pr(4)], False)) as gql:
            result = m.fetch_prs_created_since(OWNER_NAME, "r", self.SINCE)
        assert [p["number"] for p in result] == [4]
        assert gql.call_count == 1  # no overflow query for the human PR

    def test_nested_page_cap_raises(self) -> None:
        pr = _pr(7)
        pr["reviews"] = {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "r1"}}
        endless = {
            "node": {"reviews": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "r2"}}}
        }
        with (
            patch.object(m, "MAX_NESTED_PAGES", 2),
            patch.object(
                m, "gh_graphql", side_effect=[_page([pr], False), endless, endless, endless]
            ),
            pytest.raises(RuntimeError, match="exceeded 2 pages"),
        ):
            m.fetch_prs_created_since(OWNER_NAME, "r", self.SINCE)


class TestRunReport:
    def test_writes_report_for_agent_prs_only(self, tmp_path: Path) -> None:
        prs = [_pr(2), _pr(1, body="Plain.", author=HUMAN)]
        target = tmp_path / "report.md"
        with patch.object(m, "gh_graphql", return_value=_page(prs, False)):
            metrics = m.run_report(OWNER_NAME, "r", target, now=NOW)
        assert metrics.total_prs == 1
        assert "PR 2" in target.read_text(encoding="utf-8")
        assert "PR 1" not in target.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI wiring: failures must exit nonzero
# ---------------------------------------------------------------------------


class TestCli:
    def _patched(self, report: Any) -> Any:
        healthy = SimpleNamespace(status=RateLimitStatus.VERIFIED_HEALTHY)
        return (
            patch.object(stats_script, "check_workflow_rate_limit", return_value=healthy),
            patch.object(
                stats_script,
                "resolve_repo_params",
                return_value=SimpleNamespace(owner="o", repo="r"),
            ),
            patch.object(stats_script, "run_agent_intervention_report", report),
        )

    def test_api_failure_returns_2(self) -> None:
        a, b, c = self._patched(_raise)
        with a, b, c:
            assert stats_script.main(["--agent-intervention"]) == 2

    @pytest.mark.parametrize(
        "error",
        [
            subprocess.TimeoutExpired("gh", 30),
            OSError("disk"),
            KeyError("createdAt"),
            TypeError("bad node"),
        ],
        ids=["timeout", "oserror", "keyerror", "typeerror"],
    )
    def test_unexpected_failures_return_2(self, error: Exception) -> None:
        def boom(*_: Any) -> None:
            raise error

        a, b, c = self._patched(boom)
        with a, b, c:
            assert stats_script.main(["--agent-intervention"]) == 2

    def test_unresolved_repo_root_returns_1_and_writes_nothing(self) -> None:
        a, b, c = self._patched(lambda *_: pytest.fail("report must not run"))
        with a, b, c, patch.object(stats_script, "get_repo_root", return_value=None):
            assert stats_script.main(["--agent-intervention"]) == 1

    def test_cwd_outside_repo_root_returns_1(self, tmp_path: Path) -> None:
        a, b, c = self._patched(lambda *_: pytest.fail("report must not run"))
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        with a, b, c, patch.object(stats_script, "get_repo_root", return_value=elsewhere):
            assert stats_script.main(["--agent-intervention"]) == 1

    def test_success_returns_0_and_skips_reviewer_stats(self) -> None:
        metrics = m.build_metrics([], NOW - timedelta(days=30), NOW, OWNER_NAME)
        a, b, c = self._patched(lambda *_: metrics)
        with a, b, c, patch.object(stats_script, "get_all_prs_with_comments") as reviewer_fetch:
            assert stats_script.main(["--agent-intervention"]) == 0
        reviewer_fetch.assert_not_called()


def _raise(*_: Any) -> None:
    raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# Workflow wiring: parsed structure, not substrings
# ---------------------------------------------------------------------------

WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "update-reviewer-stats.yml"
)


class TestWorkflowWiring:
    @staticmethod
    def _steps() -> dict[str, dict[str, Any]]:
        doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        return {s["name"]: s for s in doc["jobs"]["update-stats"]["steps"]}

    def test_intervention_report_runs_after_the_existing_stats_commit(self) -> None:
        names = list(self._steps())
        assert names.index("Commit updated stats") < names.index(
            "Build agent PR intervention report"
        )
        assert names.index("Build agent PR intervention report") < names.index(
            "Commit agent PR intervention report"
        )

    def test_each_report_is_committed_by_its_own_step(self) -> None:
        steps = self._steps()
        assert m.REPORT_PATH in steps["Commit agent PR intervention report"]["run"]
        assert m.REPORT_PATH not in steps["Commit updated stats"]["run"]
        assert "--agent-intervention" in steps["Build agent PR intervention report"]["run"]

    def test_report_does_not_depend_on_the_stats_steps_succeeding(self) -> None:
        build = self._steps()["Build agent PR intervention report"]
        assert "!cancelled()" in build["if"]
        assert build["timeout-minutes"] > 0

    def test_report_commit_requires_a_successful_build(self) -> None:
        steps = self._steps()
        build, commit = (
            steps["Build agent PR intervention report"],
            steps["Commit agent PR intervention report"],
        )
        assert f"steps.{build['id']}.outcome == 'success'" in commit["if"]
        assert commit["timeout-minutes"] > 0
