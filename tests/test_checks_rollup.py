"""Tests for scripts/github_core/checks_rollup.py rollup evaluation.

Covers the superseded-run dedupe and the context pagination added for
Issue #3978. Every GraphQL call is a MagicMock, so no network is touched.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

from scripts.github_core.checks_rollup import (
    latest_contexts_by_run,
    rollup_has_failing_checks,
)

# ---------------------------------------------------------------------------
# Fixtures builders
# ---------------------------------------------------------------------------


def _check_run(
    name: str, conclusion: str, completed_at: str, workflow: str = "CI"
) -> dict[str, Any]:
    return {
        "name": name,
        "status": "COMPLETED",
        "conclusion": conclusion,
        "startedAt": completed_at,
        "completedAt": completed_at,
        "checkSuite": {"workflowRun": {"workflow": {"name": workflow}}},
    }


def _rollup(
    nodes: list[dict[str, Any]],
    *,
    state: str = "FAILURE",
    total_count: int | None = None,
    has_next: bool = False,
    end_cursor: str = "",
) -> dict[str, Any]:
    contexts: dict[str, Any] = {
        "nodes": nodes,
        "pageInfo": {"hasNextPage": has_next, "endCursor": end_cursor},
    }
    if total_count is not None:
        contexts["totalCount"] = total_count
    return {"state": state, "contexts": contexts}


def _page(
    nodes: list[dict[str, Any]], *, has_next: bool = False, end_cursor: str = ""
) -> dict[str, Any]:
    return {
        "repository": {
            "object": {
                "statusCheckRollup": {
                    "contexts": {
                        "nodes": nodes,
                        "pageInfo": {
                            "hasNextPage": has_next,
                            "endCursor": end_cursor,
                        },
                    }
                }
            }
        }
    }


def _evaluate(rollup: dict[str, Any] | None, graphql: Any = None, **kwargs: Any) -> bool:
    return rollup_has_failing_checks(
        rollup,
        owner="rjmurillo",
        repo="ai-agents",
        oid="308e2094",
        pr_number=4040,
        graphql=graphql or MagicMock(),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# latest_contexts_by_run
# ---------------------------------------------------------------------------


class TestLatestContextsByRun:
    def test_keeps_the_most_recent_run_per_name(self):
        nodes = [
            _check_run("Validate PR", "FAILURE", "2026-07-30T10:00:00Z", "PR Validation"),
            _check_run("Validate PR", "SUCCESS", "2026-07-30T11:00:00Z", "PR Validation"),
        ]

        winners = latest_contexts_by_run(nodes)

        assert list(winners) == [("Validate PR", "PR Validation")]
        assert winners[("Validate PR", "PR Validation")]["conclusion"] == "SUCCESS"

    def test_breaks_timestamp_ties_on_fetch_order(self):
        nodes = [
            _check_run("ci", "FAILURE", "2026-07-30T10:00:00Z"),
            _check_run("ci", "SUCCESS", "2026-07-30T10:00:00Z"),
        ]

        assert latest_contexts_by_run(nodes)[("ci", "CI")]["conclusion"] == "SUCCESS"

    def test_a_node_with_a_timestamp_beats_one_without(self):
        nodes = [
            _check_run("ci", "SUCCESS", "2026-07-30T10:00:00Z"),
            {
                "name": "ci",
                "conclusion": "FAILURE",
                "checkSuite": {"workflowRun": {"workflow": {"name": "CI"}}},
            },
        ]

        assert latest_contexts_by_run(nodes)[("ci", "CI")]["conclusion"] == "SUCCESS"

    def test_resolves_status_context_names_from_context_field(self):
        nodes = [
            {
                "context": "legacy/build",
                "state": "FAILURE",
                "createdAt": "2026-01-01T00:00:00Z",
            }
        ]

        assert list(latest_contexts_by_run(nodes)) == [("legacy/build", "")]

    def test_drops_falsy_nodes(self):
        assert latest_contexts_by_run([None, {}]) == {}

    def test_same_name_in_two_workflows_stays_in_two_groups(self):
        """PR 4069 shape: concurrent siblings, not re-runs of each other."""
        nodes = [
            _check_run(
                "Check Changed Paths", "FAILURE", "2026-07-31T01:26:07Z",
                "Validate Path Normalization",
            ),
            _check_run(
                "Check Changed Paths", "SUCCESS", "2026-07-31T01:26:11Z",
                "Python Tests",
            ),
        ]

        winners = latest_contexts_by_run(nodes)

        assert len(winners) == 2
        assert winners[
            ("Check Changed Paths", "Validate Path Normalization")
        ]["conclusion"] == "FAILURE"

    def test_check_runs_without_a_workflow_group_on_name_alone(self):
        """An app check run carries no workflowRun; recency still dedupes it."""
        nodes = [
            {"name": "codecov", "conclusion": "FAILURE",
             "completedAt": "2026-07-30T10:00:00Z", "checkSuite": {"workflowRun": None}},
            {"name": "codecov", "conclusion": "SUCCESS",
             "completedAt": "2026-07-30T11:00:00Z", "checkSuite": None},
        ]

        winners = latest_contexts_by_run(nodes)

        assert list(winners) == [("codecov", "")]
        assert winners[("codecov", "")]["conclusion"] == "SUCCESS"


# ---------------------------------------------------------------------------
# rollup_has_failing_checks: dedupe of superseded runs
# ---------------------------------------------------------------------------


class TestSupersededRuns:
    def test_stale_failure_with_a_later_success_reads_as_passing(self):
        """PR 4040 shape: rollup.state is FAILURE, every latest run is green."""
        rollup = _rollup(
            [
                _check_run("Validate PR", "FAILURE", "2026-07-30T10:00:00Z"),
                _check_run("Validate PR", "SUCCESS", "2026-07-30T11:00:00Z"),
                _check_run("lint", "SUCCESS", "2026-07-30T10:30:00Z"),
            ],
            state="FAILURE",
            total_count=3,
        )

        assert _evaluate(rollup) is False

    def test_stale_success_with_a_later_failure_reads_as_failing(self):
        """The inverse direction: recency wins over verdict precedence."""
        rollup = _rollup(
            [
                _check_run("Validate PR", "SUCCESS", "2026-07-30T10:00:00Z"),
                _check_run("Validate PR", "FAILURE", "2026-07-30T11:00:00Z"),
            ],
            state="SUCCESS",
            total_count=2,
        )

        assert _evaluate(rollup) is True

    def test_a_later_success_in_another_workflow_cannot_mask_a_failure(self):
        """PR 4069 shape: same job name, different workflows, one second apart.

        Grouping on the check name alone let the 01:26:11Z SUCCESS from
        Python Tests discard three real FAILURE runs of the same name.
        """
        rollup = _rollup(
            [
                _check_run("Check Changed Paths", "FAILURE", "2026-07-31T01:26:07Z",
                           "Validate Path Normalization"),
                _check_run("Check Changed Paths", "FAILURE", "2026-07-31T01:26:08Z",
                           "Validate Plugin Version Bump"),
                _check_run("Check Changed Paths", "FAILURE", "2026-07-31T01:26:10Z",
                           "Skillbook Validation"),
                _check_run("Check Changed Paths", "SUCCESS", "2026-07-31T01:26:11Z",
                           "Python Tests"),
            ],
            state="FAILURE",
            total_count=4,
        )

        assert _evaluate(rollup) is True

    def test_a_rerun_in_a_new_check_suite_still_supersedes(self):
        """PR 4040 shape: the re-run changes check suite, not workflow.

        Keying the group on the check-suite id instead of the workflow name
        would split these two rows and reinstate the Issue #3978 defect.
        """
        stale = _check_run("Validate PR", "FAILURE", "2026-07-31T03:05:09Z",
                           "PR Validation")
        stale["checkSuite"]["databaseId"] = 82979074639
        fresh = _check_run("Validate PR", "SUCCESS", "2026-07-31T03:35:49Z",
                           "PR Validation")
        fresh["checkSuite"]["databaseId"] = 82982663213
        rollup = _rollup([stale, fresh], state="FAILURE", total_count=2)

        assert _evaluate(rollup) is False

    def test_a_status_context_never_groups_with_a_check_run_of_the_same_name(self):
        """A commit status and an Actions job can share a name; both must count."""
        rollup = _rollup(
            [
                {"context": "build", "state": "FAILURE",
                 "createdAt": "2026-07-30T10:00:00Z"},
                _check_run("build", "SUCCESS", "2026-07-30T11:00:00Z", "CI"),
            ],
            state="FAILURE",
            total_count=2,
        )

        assert _evaluate(rollup) is True

    def test_non_failure_conclusions_that_state_used_to_catch_still_fail(self):
        for conclusion in ("TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STALE",
                           "STARTUP_FAILURE"):
            rollup = _rollup(
                [_check_run("ci", conclusion, "2026-07-30T10:00:00Z")],
                state="SUCCESS",
                total_count=1,
            )

            assert _evaluate(rollup) is True, conclusion

    def test_status_context_failure_without_a_name_key(self):
        rollup = _rollup(
            [{"context": "legacy/build", "state": "FAILURE",
              "createdAt": "2026-07-30T10:00:00Z"}],
            state="SUCCESS",
            total_count=1,
        )

        assert _evaluate(rollup) is True

    def test_pending_latest_run_is_not_a_failure(self):
        rollup = _rollup(
            [
                _check_run("ci", "FAILURE", "2026-07-30T10:00:00Z"),
                {"name": "ci", "status": "IN_PROGRESS", "conclusion": None,
                 "startedAt": "2026-07-30T11:00:00Z", "completedAt": None,
                 "checkSuite": {"workflowRun": {"workflow": {"name": "CI"}}}},
            ],
            state="FAILURE",
            total_count=2,
        )

        assert _evaluate(rollup) is False

    def test_empty_contexts_read_as_passing(self):
        assert _evaluate(_rollup([], state="FAILURE", total_count=0)) is False

    def test_missing_page_info_reads_the_nodes_it_has(self):
        rollup = {
            "state": "FAILURE",
            "contexts": {"nodes": [_check_run("ci", "SUCCESS", "2026-07-30T10:00:00Z")]},
        }

        assert _evaluate(rollup) is False

    def test_none_rollup_reads_as_passing(self):
        assert _evaluate(None) is False

    def test_missing_contexts_key_reads_as_passing(self):
        assert _evaluate({"state": "FAILURE"}) is False


# ---------------------------------------------------------------------------
# rollup_has_failing_checks: pagination
# ---------------------------------------------------------------------------


class TestPagination:
    def test_fetches_the_tail_and_finds_a_failure_in_it(self):
        head = [_check_run(f"check-{i}", "SUCCESS", "2026-07-30T10:00:00Z")
                for i in range(100)]
        tail = [_check_run("tail-check", "FAILURE", "2026-07-30T10:05:00Z")]
        graphql = MagicMock(return_value=_page(tail))
        rollup = _rollup(head, state="SUCCESS", total_count=101,
                         has_next=True, end_cursor="CUR100")

        assert _evaluate(rollup, graphql) is True
        assert graphql.call_count == 1
        assert graphql.call_args[0][1]["cursor"] == "CUR100"
        assert graphql.call_args[0][1]["oid"] == "308e2094"

    def test_a_tail_success_supersedes_a_head_failure_for_the_same_name(self):
        head = [_check_run("Validate PR", "FAILURE", "2026-07-30T10:00:00Z")]
        tail = [_check_run("Validate PR", "SUCCESS", "2026-07-30T11:00:00Z")]
        graphql = MagicMock(return_value=_page(tail))
        rollup = _rollup(head, state="FAILURE", total_count=2,
                         has_next=True, end_cursor="CUR1")

        assert _evaluate(rollup, graphql) is False

    def test_follows_multiple_pages(self):
        graphql = MagicMock(
            side_effect=[
                _page([_check_run("a", "SUCCESS", "2026-07-30T10:00:00Z")],
                      has_next=True, end_cursor="CUR2"),
                _page([_check_run("b", "FAILURE", "2026-07-30T10:00:00Z")]),
            ]
        )
        rollup = _rollup(
            [_check_run("c", "SUCCESS", "2026-07-30T10:00:00Z")],
            state="SUCCESS", total_count=3, has_next=True, end_cursor="CUR1",
        )

        assert _evaluate(rollup, graphql) is True
        assert graphql.call_count == 2
        assert graphql.call_args_list[1][0][1]["cursor"] == "CUR2"


# ---------------------------------------------------------------------------
# rollup_has_failing_checks: incomplete sets fall back to rollup.state
# ---------------------------------------------------------------------------


class TestIncompleteFallsBackToState:
    def _incomplete_rollup(self, state: str) -> dict[str, Any]:
        return _rollup(
            [_check_run("ci", "SUCCESS", "2026-07-30T10:00:00Z")],
            state=state, total_count=127, has_next=True, end_cursor="CUR1",
        )

    def test_page_error_falls_back_to_failure_state(self, caplog):
        graphql = MagicMock(side_effect=RuntimeError("gh api failed"))

        with caplog.at_level(logging.ERROR):
            result = _evaluate(self._incomplete_rollup("FAILURE"), graphql)

        assert result is True
        assert "incomplete status-check contexts" in caplog.text

    def test_page_error_falls_back_to_success_state(self):
        graphql = MagicMock(side_effect=RuntimeError("gh api failed"))

        assert _evaluate(self._incomplete_rollup("SUCCESS"), graphql) is False

    def test_short_read_against_total_count_falls_back(self, caplog):
        graphql = MagicMock(
            return_value=_page([_check_run("d", "SUCCESS", "2026-07-30T10:00:00Z")])
        )

        with caplog.at_level(logging.ERROR):
            result = _evaluate(self._incomplete_rollup("FAILURE"), graphql)

        assert result is True
        assert "2 fetched of 127" in caplog.text

    def test_missing_oid_cannot_page_and_falls_back(self):
        graphql = MagicMock()

        result = rollup_has_failing_checks(
            self._incomplete_rollup("FAILURE"),
            owner="rjmurillo",
            repo="ai-agents",
            oid="",
            graphql=graphql,
        )

        assert result is True
        graphql.assert_not_called()

    def test_broken_cursor_chain_falls_back(self):
        graphql = MagicMock(return_value=_page([], has_next=True, end_cursor=""))

        assert _evaluate(self._incomplete_rollup("FAILURE"), graphql) is True

    def test_empty_end_cursor_on_the_first_hop_falls_back(self):
        graphql = MagicMock()
        rollup = _rollup(
            [_check_run("ci", "SUCCESS", "2026-07-30T10:00:00Z")],
            state="ERROR", total_count=127, has_next=True, end_cursor="",
        )

        assert _evaluate(rollup, graphql) is True
        graphql.assert_not_called()

    def test_runaway_pagination_is_capped_and_falls_back(self):
        graphql = MagicMock(return_value=_page([], has_next=True, end_cursor="CUR"))
        rollup = _rollup(
            [_check_run("ci", "SUCCESS", "2026-07-30T10:00:00Z")],
            state="FAILURE", has_next=True, end_cursor="CUR1",
        )

        assert _evaluate(rollup, graphql) is True
        assert graphql.call_count == 50

    def test_no_total_count_and_a_clean_page_walk_decides_from_contexts(self):
        """State says SUCCESS; the only True can come from the context set."""
        graphql = MagicMock(
            return_value=_page([_check_run("b", "SUCCESS", "2026-07-30T10:00:00Z")])
        )
        rollup = _rollup(
            [_check_run("a", "FAILURE", "2026-07-30T09:00:00Z")],
            state="SUCCESS", has_next=True, end_cursor="CUR1",
        )

        assert _evaluate(rollup, graphql) is True
