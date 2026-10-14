"""Workflow-run events and error classes in checks_rest (issues #6391, #6425)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts.github_core import checks_rest
from tests.test_github_core_checks_rest import _RUN_URL, _fake_api, _pr_payload


class TestFetchWorkflowRuns:
    def test_maps_run_id_to_the_run_and_reports_complete_pages(self):
        pages = [
            {
                "total_count": 2,
                "workflow_runs": [
                    {"id": 100, "event": "pull_request", "run_attempt": 1},
                    {"id": 101, "event": "push", "run_attempt": 3},
                ],
            }
        ]
        with patch.object(checks_rest, "_run_gh_api", return_value=pages) as api:
            by_id, complete = checks_rest._fetch_workflow_runs("o", "r", "abc123")
        assert by_id[100]["event"] == "pull_request"
        assert by_id[101]["run_attempt"] == 3
        assert complete is True
        assert "actions/runs?head_sha=abc123" in api.call_args.args[0][-1]

    def test_truncated_pages_report_incomplete(self):
        pages = [{"total_count": 9, "workflow_runs": [{"id": 1, "event": "push"}]}]
        with patch.object(checks_rest, "_run_gh_api", return_value=pages):
            _, complete = checks_rest._fetch_workflow_runs("o", "r", "abc123")
        assert complete is False

    def test_rows_without_an_integer_id_are_skipped(self):
        pages = [{"total_count": 2, "workflow_runs": [{"event": "push"}, {"id": "7"}]}]
        with patch.object(checks_rest, "_run_gh_api", return_value=pages):
            by_id, _ = checks_rest._fetch_workflow_runs("o", "r", "abc123")
        assert by_id == {}

    def test_failure_propagates_so_the_fallback_does_not_guess_the_event(self):
        with patch.object(checks_rest, "_run_gh_api", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                checks_rest._fetch_workflow_runs("o", "r", "abc123")


class TestNodeEvents:
    def test_workflow_run_event_and_attempt_come_from_the_run_map(self):
        node = checks_rest.to_graphql_check_run(
            {"name": "build", "status": "completed", "details_url": _RUN_URL},
            {987654: {"id": 987654, "event": "pull_request", "run_attempt": 2}},
        )
        assert node["checkSuite"]["workflowRun"] == {
            "databaseId": 987654,
            "runAttempt": 2,
            "event": "pull_request",
        }

    def test_run_id_missing_from_the_map_keeps_event_unknown(self):
        node = checks_rest.to_graphql_check_run(
            {"name": "build", "status": "completed", "details_url": _RUN_URL},
            {1: {"id": 1, "event": "push", "run_attempt": 1}},
        )
        assert node["checkSuite"]["workflowRun"]["event"] is None


class TestFetchChecksRestRuns:
    def test_check_run_nodes_carry_the_event_of_their_workflow_run(self):
        routes = {
            "repos/o/r/pulls/42": _pr_payload(),
            "repos/o/r/commits/abc123/check-runs": [
                {
                    "total_count": 2,
                    "check_runs": [
                        {
                            "name": "Tests",
                            "status": "completed",
                            "conclusion": "failure",
                            "details_url": "https://github.com/o/r/actions/runs/100/job/1",
                        },
                        {
                            "name": "Tests",
                            "status": "completed",
                            "conclusion": "success",
                            "details_url": "https://github.com/o/r/actions/runs/101/job/2",
                        },
                    ],
                }
            ],
            "repos/o/r/commits/abc123/status": [{"total_count": 0, "statuses": []}],
            "repos/o/r/actions/runs": [
                {
                    "total_count": 2,
                    "workflow_runs": [
                        {"id": 100, "event": "pull_request", "run_attempt": 1},
                        {"id": 101, "event": "push", "run_attempt": 1},
                    ],
                }
            ],
        }
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            snap = checks_rest.fetch_checks_rest("o", "r", 42)
        events = [n["checkSuite"]["workflowRun"]["event"] for n in snap["Nodes"]]
        assert events == ["pull_request", "push"]
        assert snap["PagesComplete"] is True

    def test_truncated_workflow_runs_mark_pages_incomplete(self):
        routes = {
            "repos/o/r/pulls/42": _pr_payload(),
            "repos/o/r/commits/abc123/check-runs": [{"total_count": 0, "check_runs": []}],
            "repos/o/r/commits/abc123/status": [{"total_count": 0, "statuses": []}],
            "repos/o/r/actions/runs": [
                {"total_count": 4, "workflow_runs": [{"id": 1, "event": "push"}]}
            ],
        }
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            assert checks_rest.fetch_checks_rest("o", "r", 42)["PagesComplete"] is False

    def test_workflow_runs_failure_fails_the_fetch(self):
        routes = {
            "repos/o/r/pulls/42": _pr_payload(),
            "repos/o/r/commits/abc123/check-runs": [{"total_count": 0, "check_runs": []}],
            "repos/o/r/commits/abc123/status": [{"total_count": 0, "statuses": []}],
            "repos/o/r/actions/runs": RuntimeError("REST request failed: boom"),
        }
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            with pytest.raises(RuntimeError, match="boom"):
                checks_rest.fetch_checks_rest("o", "r", 42)

    @pytest.mark.parametrize("head", ["abc123", ["x"], 7, None])
    def test_non_dict_head_raises_runtime_error_not_attribute_error(self, head):
        routes = {"repos/o/r/pulls/42": _pr_payload(head=head)}
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            with pytest.raises(RuntimeError, match="no head sha"):
                checks_rest.fetch_checks_rest("o", "r", 42)

    @pytest.mark.parametrize("base", ["main", ["x"], 7, None])
    def test_non_dict_base_reads_as_no_base_branch(self, base):
        routes = {
            "repos/o/r/pulls/42": _pr_payload(base=base),
            "repos/o/r/commits/abc123/check-runs": [{"total_count": 0, "check_runs": []}],
            "repos/o/r/commits/abc123/status": [{"total_count": 0, "statuses": []}],
        }
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            assert checks_rest.fetch_checks_rest("o", "r", 42)["BaseBranch"] is None

    def test_pull_request_404_raises_the_not_found_subclass(self):
        routes = {"repos/o/r/pulls/42": RuntimeError("REST request failed: Not Found (HTTP 404)")}
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            with pytest.raises(checks_rest.PullRequestNotFoundError, match="HTTP 404"):
                checks_rest.fetch_checks_rest("o", "r", 42)

    @pytest.mark.parametrize(
        "endpoint",
        [
            "repos/o/r/commits/abc123/check-runs",
            "repos/o/r/commits/abc123/status",
            "repos/o/r/actions/runs",
        ],
    )
    def test_secondary_404_is_not_reported_as_a_missing_pull_request(self, endpoint):
        routes = {
            "repos/o/r/pulls/42": _pr_payload(),
            "repos/o/r/commits/abc123/check-runs": [{"total_count": 0, "check_runs": []}],
            "repos/o/r/commits/abc123/status": [{"total_count": 0, "statuses": []}],
            endpoint: RuntimeError("REST request failed: Not Found (HTTP 404)"),
        }
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            with pytest.raises(RuntimeError) as info:
                checks_rest.fetch_checks_rest("o", "r", 42)
        assert not isinstance(info.value, checks_rest.PullRequestNotFoundError)


class TestCheckRunsFilter:
    def test_check_runs_request_asks_for_every_run_not_only_the_latest(self):
        routes = {
            "repos/o/r/pulls/42": _pr_payload(),
            "repos/o/r/commits/abc123/check-runs": [{"total_count": 0, "check_runs": []}],
            "repos/o/r/commits/abc123/status": [{"total_count": 0, "statuses": []}],
        }
        fake = _fake_api(routes)
        with patch.object(checks_rest, "_run_gh_api", side_effect=fake) as api:
            checks_rest.fetch_checks_rest("o", "r", 42)
        check_run_calls = [
            c.args[0][-1] for c in api.call_args_list if "/check-runs" in c.args[0][-1]
        ]
        assert len(check_run_calls) == 1
        assert "filter=all" in check_run_calls[0]
