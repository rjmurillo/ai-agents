"""Tests for scripts/agent_pr_intervention_metrics.py and its CLI wiring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from scripts import agent_pr_intervention_metrics as m
from scripts import update_reviewer_signal_stats as stats_script

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
TRAILER = "Body.\n\n\U0001f916 Generated with [Claude Code](https://claude.com/claude-code)"


def _actor(login: str, typename: str = "User", database_id: int | None = None) -> dict[str, Any]:
    return {"login": login, "__typename": typename, "databaseId": database_id}


BOT = _actor("coderabbitai", "Bot")
HUMAN = _actor("alice")
OWNER = _actor("rjmurillo")


def _thread(first_author: dict[str, Any]) -> dict[str, Any]:
    """A review thread as fetched: only the first comment's author is requested."""
    return {"comments": {"nodes": [{"author": first_author}]}}


def _pr(
    number: int = 1,
    *,
    body: str = TRAILER,
    author: dict[str, Any] | None = None,
    state: str = "MERGED",
    merged: bool = True,
    days_old: float = 5,
    threads: list[dict[str, Any]] | None = None,
    reviews: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"PR_{number}",
        "number": number,
        "title": f"PR {number}",
        "url": f"https://github.com/o/r/pull/{number}",
        "state": state,
        "merged": merged,
        "createdAt": (NOW - timedelta(days=days_old)).isoformat(),
        "body": body,
        "author": author or OWNER,
        "reviews": {"nodes": reviews or [], "pageInfo": {"hasNextPage": False}},
        "reviewThreads": {"nodes": threads or [], "pageInfo": {"hasNextPage": False}},
    }


# ---------------------------------------------------------------------------
# Agent-author detection
# ---------------------------------------------------------------------------


class TestIsAgentPr:
    def test_body_trailer_marks_agent_pr_under_owner_login(self) -> None:
        assert m.is_agent_pr(_pr(author=OWNER))

    def test_no_trailer_and_human_author_is_not_agent(self) -> None:
        assert not m.is_agent_pr(_pr(body="Plain description.", author=HUMAN))

    def test_coding_agent_author_without_trailer_is_agent(self) -> None:
        coding_agent = _actor("copilot-swe-agent", "Bot", 198982749)
        assert m.is_agent_pr(_pr(body="Plain.", author=coding_agent))

    def test_repository_bot_user_account_is_agent(self) -> None:
        assert m.is_agent_pr(_pr(body="Plain.", author=_actor("rjmurillo-bot")))

    def test_dependency_bot_is_not_agent(self) -> None:
        assert not m.is_agent_pr(_pr(body="Bump x.", author=_actor("renovate", "Bot")))

    def test_null_body_and_null_author_is_not_agent(self) -> None:
        pr = _pr(body="")
        pr["body"] = None
        pr["author"] = None
        assert not m.is_agent_pr(pr)


# ---------------------------------------------------------------------------
# Intervention counting
# ---------------------------------------------------------------------------


class TestCountInterventions:
    def test_bot_opened_thread_is_ignored(self) -> None:
        assert m.count_interventions(_pr(threads=[_thread(BOT), _thread(BOT)])) == 0

    def test_human_opened_thread_counts_once(self) -> None:
        assert m.count_interventions(_pr(threads=[_thread(HUMAN), _thread(BOT)])) == 1

    def test_owner_reply_in_bot_thread_is_not_counted(self) -> None:
        # The agent replies as the owner; only the first comment decides, and the
        # query requests only that comment, so replies are not even fetched.
        assert m.count_interventions(_pr(threads=[_thread(BOT)])) == 0

    def test_approval_with_no_comment_is_not_an_intervention(self) -> None:
        review = {"state": "APPROVED", "author": HUMAN}
        assert m.count_interventions(_pr(reviews=[review])) == 0

    def test_human_changes_requested_counts(self) -> None:
        review = {"state": "CHANGES_REQUESTED", "author": HUMAN}
        assert m.count_interventions(_pr(reviews=[review])) == 1

    def test_bot_changes_requested_is_ignored(self) -> None:
        review = {"state": "CHANGES_REQUESTED", "author": BOT}
        assert m.count_interventions(_pr(reviews=[review])) == 0

    def test_commented_review_from_human_is_not_counted(self) -> None:
        review = {"state": "COMMENTED", "author": HUMAN}
        assert m.count_interventions(_pr(reviews=[review])) == 0

    def test_bot_without_bot_typename_is_caught_by_login(self) -> None:
        suffixed = _actor("some-tool[bot]")
        assert m.count_interventions(_pr(threads=[_thread(suffixed)])) == 0

    def test_deleted_account_thread_counts_as_human(self) -> None:
        thread = {"comments": {"nodes": [{"author": None}]}}
        assert m.count_interventions(_pr(threads=[thread])) == 1

    def test_empty_thread_is_skipped(self) -> None:
        assert m.count_interventions(_pr(threads=[{"comments": {"nodes": []}}])) == 0


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


class TestBuildMetrics:
    def _build(self, prs: list[dict[str, Any]]) -> m.InterventionMetrics:
        return m.build_metrics(prs, NOW - timedelta(days=30), NOW)

    def test_splits_merged_unmerged_and_open(self) -> None:
        prs = [
            _pr(1),
            _pr(2, state="CLOSED", merged=False),
            _pr(3, state="OPEN", merged=False),
        ]
        result = self._build(prs)
        assert {k: c.prs for k, c in result.cohorts.items()} == {
            m.MERGED: 1,
            m.UNMERGED: 1,
            m.OPEN: 1,
        }

    def test_zero_rate_and_counts(self) -> None:
        prs = [
            _pr(1),
            _pr(2, threads=[_thread(HUMAN)]),
            _pr(3, threads=[_thread(HUMAN), _thread(HUMAN), _thread(HUMAN)]),
            _pr(4),
        ]
        merged = self._build(prs).cohorts[m.MERGED]
        assert merged.prs == 4
        assert merged.zero_touch == 2
        assert merged.zero_rate == 0.5
        assert merged.interventions == 4
        assert merged.median_when_intervened == 2

    def test_human_authored_prs_are_discarded(self) -> None:
        prs = [_pr(1, body="Plain.", author=HUMAN, threads=[_thread(HUMAN)])]
        assert self._build(prs).total_prs == 0

    def test_pr_older_than_window_is_excluded(self) -> None:
        assert self._build([_pr(1, days_old=31)]).total_prs == 0

    def test_empty_cohort_has_no_rate(self) -> None:
        result = self._build([])
        assert result.cohorts[m.MERGED].zero_rate is None
        assert result.cohorts[m.MERGED].median_when_intervened is None

    def test_zero_touch_sample_lists_only_merged_zero_intervention_prs(self) -> None:
        prs = [
            _pr(1),
            _pr(2, threads=[_thread(HUMAN)]),
            _pr(3, state="CLOSED", merged=False),
        ]
        assert [p["number"] for p in self._build(prs).zero_touch_merged] == [1]

    def test_status_of_each_state(self) -> None:
        assert m.pr_status(_pr(state="MERGED", merged=True)) == m.MERGED
        assert m.pr_status(_pr(state="CLOSED", merged=False)) == m.UNMERGED
        assert m.pr_status(_pr(state="OPEN", merged=False)) == m.OPEN


class TestRender:
    def test_report_has_table_sample_and_definitions(self) -> None:
        prs = [_pr(n) for n in range(1, 4)]
        metrics = m.build_metrics(prs, NOW - timedelta(days=30), NOW)
        text = m.render_report(metrics, NOW)
        assert "| merged | 3 | 3 | 100% | 0 | n/a |" in text
        assert "[#3](https://github.com/o/r/pull/3): PR 3" in text
        assert "## Definitions" in text
        assert "2026-10-11 to 2026-11-10" in text
        assert not any(ch in text for ch in (chr(0x2014), chr(0x2013)))

    def test_sample_is_capped_and_spread(self) -> None:
        prs = [_pr(n) for n in range(1, 41)]
        metrics = m.build_metrics(prs, NOW - timedelta(days=30), NOW)
        text = m.render_report(metrics, NOW)
        assert text.count("- [#") == m.ZERO_TOUCH_SAMPLE_SIZE
        assert "10 of 40 merged PRs" in text

    def test_empty_sample_prints_none(self) -> None:
        metrics = m.build_metrics([], NOW - timedelta(days=30), NOW)
        assert "- none" in m.render_report(metrics, NOW)

    def test_title_brackets_are_escaped(self) -> None:
        assert m._escape_title("fix [a]\nb") == "fix \\[a\\] b"


class TestWriteReport:
    def test_creates_parent_and_leaves_no_temp_file(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "report.md"
        m.write_report(target, "hello")
        assert target.read_text(encoding="utf-8") == "hello"
        assert [p.name for p in target.parent.iterdir()] == ["report.md"]


# ---------------------------------------------------------------------------
# Lossless fetching
# ---------------------------------------------------------------------------


def _page(prs: list[dict[str, Any]], has_next: bool, cursor: str | None = "c1") -> dict[str, Any]:
    return {
        "repository": {
            "pullRequests": {
                "nodes": prs,
                "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
            }
        }
    }


class TestFetch:
    SINCE = NOW - timedelta(days=30)

    def test_pages_until_no_next_page(self) -> None:
        pages = [_page([_pr(2)], True, "c1"), _page([_pr(1)], False, None)]
        with patch.object(m, "gh_graphql", side_effect=pages) as gql:
            result = m.fetch_prs_created_since("o", "r", self.SINCE)
        assert [p["number"] for p in result] == [2, 1]
        assert gql.call_args_list[1].args[1]["cursor"] == "c1"

    def test_stops_at_first_pr_older_than_window(self) -> None:
        pages = [_page([_pr(2), _pr(1, days_old=40)], True), _page([_pr(0)], False)]
        with patch.object(m, "gh_graphql", side_effect=pages) as gql:
            result = m.fetch_prs_created_since("o", "r", self.SINCE)
        assert [p["number"] for p in result] == [2]
        assert gql.call_count == 1

    def test_missing_cursor_raises(self) -> None:
        with (
            patch.object(m, "gh_graphql", return_value=_page([_pr(1)], True, None)),
            pytest.raises(RuntimeError, match="no cursor"),
        ):
            m.fetch_prs_created_since("o", "r", self.SINCE)

    def test_page_cap_raises_instead_of_warning(self) -> None:
        with (
            patch.object(m, "MAX_PR_PAGES", 2),
            patch.object(m, "gh_graphql", side_effect=lambda *_: _page([_pr(1)], True)),
            pytest.raises(RuntimeError, match="exceeded 2 pages"),
        ):
            m.fetch_prs_created_since("o", "r", self.SINCE)

    def test_null_repository_raises(self) -> None:
        with (
            patch.object(m, "gh_graphql", return_value={"repository": None}),
            pytest.raises(RuntimeError, match="Could not read"),
        ):
            m.fetch_prs_created_since("o", "r", self.SINCE)

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
            result = m.fetch_prs_created_since("o", "r", self.SINCE)
        assert m.count_interventions(result[0]) == 1
        assert gql.call_args_list[1].args[1] == {"id": "PR_7", "cursor": "t1"}

    def test_overflowing_list_without_cursor_raises(self) -> None:
        pr = _pr(7)
        pr["reviews"] = {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": None}}
        with (
            patch.object(m, "gh_graphql", return_value=_page([pr], False)),
            pytest.raises(RuntimeError, match="no cursor"),
        ):
            m.fetch_prs_created_since("o", "r", self.SINCE)

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
            m.fetch_prs_created_since("o", "r", self.SINCE)


class TestRunReport:
    def test_writes_report_for_agent_prs_only(self, tmp_path: Path) -> None:
        prs = [_pr(2), _pr(1, body="Plain.", author=HUMAN)]
        target = tmp_path / "report.md"
        with patch.object(m, "gh_graphql", return_value=_page(prs, False)):
            metrics = m.run_report("o", "r", target, now=NOW)
        assert metrics.total_prs == 1
        assert "PR 2" in target.read_text(encoding="utf-8")
        assert "PR 1" not in target.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI wiring: failures must exit nonzero
# ---------------------------------------------------------------------------


class TestCli:
    def _patched(self, report: Any) -> Any:
        healthy = SimpleNamespace(status=stats_script.RateLimitStatus.VERIFIED_HEALTHY)
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

    def test_success_returns_0_and_skips_reviewer_stats(self) -> None:
        metrics = m.build_metrics([], NOW - timedelta(days=30), NOW)
        a, b, c = self._patched(lambda *_: metrics)
        with a, b, c, patch.object(stats_script, "get_all_prs_with_comments") as reviewer_fetch:
            assert stats_script.main(["--agent-intervention"]) == 0
        reviewer_fetch.assert_not_called()


def _raise(*_: Any) -> None:
    raise RuntimeError("boom")
