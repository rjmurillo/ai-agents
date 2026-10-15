"""Tests for scripts.github_core.checks_rest and is_rate_limit_refusal (issue #6391)."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from scripts.github_core import checks_rest
from scripts.github_core.api import is_rate_limit_refusal

_RUN_URL = "https://github.com/o/r/actions/runs/987654/job/111"


def _completed(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _commit_payload(date: str | None = "2026-10-13T10:00:00Z") -> dict:
    return {"sha": "abc123", "committer": {"date": date}}


def _fake_api(routes: dict[str, object]):
    """Return a ``_run_gh_api`` stand-in keyed on the endpoint argument.

    The head commit route defaults to a fixed committer date, so tests that do
    not care about it still pass.
    """
    routes = {
        "repos/o/r/git/commits/abc123": _commit_payload(),
        "repos/o/r/actions/runs": [{"total_count": 0, "workflow_runs": []}],
        "repos/o/r/commits/abc123/check-suites": {"total_count": 0, "check_suites": []},
        "repos/o/r": {"full_name": "o/r"},
        **routes,
    }

    def _call(args: list[str]):
        endpoint = args[-1].split("?")[0]
        if endpoint not in routes:
            raise AssertionError(f"unexpected endpoint {endpoint}")
        value = routes[endpoint]
        if isinstance(value, Exception):
            raise value
        return value

    return _call


class TestIsRateLimitRefusal:
    @pytest.mark.parametrize(
        "text",
        [
            "GraphQL request failed: API rate limit already exceeded for user ID 42.",
            "gh: API rate limit exceeded for user ID 42. (HTTP 403)",
            "You have exceeded a secondary rate limit. Please wait a few minutes.",
        ],
    )
    def test_true_for_primary_and_secondary_refusals(self, text):
        assert is_rate_limit_refusal(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "Resource not accessible by integration (HTTP 403)",
            "Could not resolve to a PullRequest with the number of 9",
            "Bad credentials (HTTP 401)",
            "HTTP 502 Bad Gateway",
            "",
        ],
    )
    def test_false_for_other_failures(self, text):
        assert is_rate_limit_refusal(text) is False


class TestRunGhApi:
    def test_returns_parsed_json_and_passes_args_to_gh_api(self):
        with patch.object(
            checks_rest.subprocess, "run", return_value=_completed(stdout='{"a": 1}')
        ) as run:
            assert checks_rest._run_gh_api(["repos/o/r/pulls/1"]) == {"a": 1}
        argv = run.call_args.args[0]
        assert argv == ["gh", "api", "repos/o/r/pulls/1"]
        assert run.call_args.kwargs["encoding"] == "utf-8"
        assert run.call_args.kwargs["errors"] == "replace"

    def test_nonzero_exit_raises_with_gh_text(self):
        failed = _completed(returncode=1, stderr="gh: Not Found (HTTP 404)")
        with patch.object(checks_rest.subprocess, "run", return_value=failed):
            with pytest.raises(RuntimeError, match="Not Found"):
                checks_rest._run_gh_api(["x"])

    def test_nonzero_exit_with_empty_output_still_raises(self):
        with patch.object(checks_rest.subprocess, "run", return_value=_completed(returncode=1)):
            with pytest.raises(RuntimeError, match="gh exited non-zero"):
                checks_rest._run_gh_api(["x"])

    def test_timeout_raises_runtime_error(self):
        timeout = subprocess.TimeoutExpired(cmd="gh", timeout=30)
        with patch.object(checks_rest.subprocess, "run", side_effect=timeout):
            with pytest.raises(RuntimeError, match="REST request failed"):
                checks_rest._run_gh_api(["x"])

    def test_non_json_body_raises(self):
        with patch.object(checks_rest.subprocess, "run", return_value=_completed(stdout="<html>")):
            with pytest.raises(RuntimeError, match="non-JSON"):
                checks_rest._run_gh_api(["x"])


class TestFetchPages:
    def test_flattens_pages_and_reads_first_total(self):
        pages = [
            {"total_count": 3, "check_runs": [{"name": "a"}, {"name": "b"}]},
            {"total_count": 3, "check_runs": [{"name": "c"}]},
        ]
        with patch.object(checks_rest, "_run_gh_api", return_value=pages) as api:
            items, total = checks_rest._fetch_pages("repos/o/r/commits/s/check-runs", "check_runs")
        assert [i["name"] for i in items] == ["a", "b", "c"]
        assert total == 3
        assert api.call_args.args[0] == [
            "--paginate",
            "--slurp",
            "repos/o/r/commits/s/check-runs?per_page=100",
        ]

    def test_empty_pages_list_yields_nothing(self):
        with patch.object(checks_rest, "_run_gh_api", return_value=[]):
            assert checks_rest._fetch_pages("e", "check_runs") == ([], 0)

    def test_missing_total_is_none(self):
        with patch.object(checks_rest, "_run_gh_api", return_value=[{"check_runs": []}]):
            assert checks_rest._fetch_pages("e", "check_runs") == ([], None)

    @pytest.mark.parametrize("payload", [{"check_runs": []}, ["not a page"], "text"])
    def test_non_page_shapes_raise(self, payload):
        with patch.object(checks_rest, "_run_gh_api", return_value=payload):
            with pytest.raises(RuntimeError, match="not a list of pages"):
                checks_rest._fetch_pages("e", "check_runs")

    def test_null_items_key_and_non_dict_items_are_skipped(self):
        pages = [{"total_count": 1, "statuses": None}, {"statuses": ["junk", {"context": "ci"}]}]
        with patch.object(checks_rest, "_run_gh_api", return_value=pages):
            items, _ = checks_rest._fetch_pages("e", "statuses")
        assert items == [{"context": "ci"}]


class TestNodeConversion:
    def test_completed_check_run_is_upper_cased_with_run_id(self):
        node = checks_rest.to_graphql_check_run(
            {
                "name": "build",
                "status": "completed",
                "conclusion": "success",
                "details_url": _RUN_URL,
            }
        )
        assert node["__typename"] == "CheckRun"
        assert node["name"] == "build"
        assert node["status"] == "COMPLETED"
        assert node["conclusion"] == "SUCCESS"
        assert node["detailsUrl"] == _RUN_URL
        assert node["checkSuite"]["workflowRun"] == {
            "databaseId": 987654,
            "runAttempt": None,
            "event": None,
        }
        assert node["isRequired"] is False

    def test_in_progress_run_has_null_conclusion(self):
        node = checks_rest.to_graphql_check_run(
            {"name": "t", "status": "in_progress", "conclusion": None}
        )
        assert node["status"] == "IN_PROGRESS"
        assert node["conclusion"] is None
        assert node["detailsUrl"] == ""

    def test_run_without_actions_url_has_no_workflow_run(self):
        node = checks_rest.to_graphql_check_run(
            {
                "name": "ext",
                "status": "completed",
                "conclusion": "failure",
                "details_url": "https://ci.example/1",
            }
        )
        assert node["checkSuite"]["workflowRun"] is None

    def test_empty_run_does_not_raise(self):
        node = checks_rest.to_graphql_check_run({})
        assert node["name"] == ""
        assert node["status"] == ""
        assert node["conclusion"] is None

    def test_status_context_maps_fields(self):
        node = checks_rest.to_graphql_status_context(
            {"context": "legacy/ci", "state": "failure", "target_url": "https://ci/2"}
        )
        assert node == {
            "__typename": "StatusContext",
            "context": "legacy/ci",
            "state": "FAILURE",
            "targetUrl": "https://ci/2",
            "isRequired": False,
        }

    def test_status_context_tolerates_missing_fields(self):
        node = checks_rest.to_graphql_status_context({})
        assert node["context"] == ""
        assert node["state"] == ""
        assert node["targetUrl"] == ""


class TestMergeFields:
    @pytest.mark.parametrize(
        ("pr", "expected"),
        [
            ({"mergeable": True, "mergeable_state": "clean"}, ("MERGEABLE", "CLEAN")),
            ({"mergeable": False, "mergeable_state": "dirty"}, ("CONFLICTING", "DIRTY")),
            ({"mergeable": None, "mergeable_state": "unknown"}, ("UNKNOWN", "UNKNOWN")),
            ({"mergeable": True, "mergeable_state": "blocked"}, ("MERGEABLE", "BLOCKED")),
            ({}, ("UNKNOWN", "UNKNOWN")),
            ({"mergeable": True, "mergeable_state": ""}, ("MERGEABLE", "UNKNOWN")),
        ],
    )
    def test_maps_rest_values_to_graphql_vocabulary(self, pr, expected):
        assert checks_rest._merge_fields(pr) == expected


def _pr_payload(**overrides):
    payload = {
        "number": 42,
        "head": {"sha": "abc123"},
        "base": {"ref": "main"},
        "mergeable": True,
        "mergeable_state": "clean",
    }
    payload.update(overrides)
    return payload


class TestFetchChecksRest:
    def test_combines_check_runs_and_statuses_for_the_head_sha(self):
        routes = {
            "repos/o/r/pulls/42": _pr_payload(),
            "repos/o/r/commits/abc123/check-runs": [
                {
                    "total_count": 1,
                    "check_runs": [
                        {"name": "build", "status": "completed", "conclusion": "success"}
                    ],
                }
            ],
            "repos/o/r/commits/abc123/status": [
                {"total_count": 1, "statuses": [{"context": "legacy", "state": "pending"}]}
            ],
        }
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            snap = checks_rest.fetch_checks_rest("o", "r", 42)
        assert snap["Number"] == 42
        assert snap["BaseBranch"] == "main"
        assert snap["MergeState"] == "MERGEABLE"
        assert snap["MergeStateStatus"] == "CLEAN"
        assert [n["__typename"] for n in snap["Nodes"]] == ["CheckRun", "StatusContext"]
        assert snap["PagesComplete"] is True

    def test_reports_the_head_commit_date_for_the_queued_grace_window(self):
        routes = {
            "repos/o/r/pulls/42": _pr_payload(),
            "repos/o/r/commits/abc123/check-runs": [{"total_count": 0, "check_runs": []}],
            "repos/o/r/commits/abc123/status": [{"total_count": 0, "statuses": []}],
        }
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            snap = checks_rest.fetch_checks_rest("o", "r", 42)
        assert snap["HeadCommittedAt"] == "2026-10-13T10:00:00Z"

    @pytest.mark.parametrize(
        "commit",
        [
            RuntimeError("REST request failed: boom"),
            _commit_payload(date=None),
            {"sha": "abc123"},
            [],
        ],
    )
    def test_unknown_head_commit_date_is_none_not_an_error(self, commit):
        routes = {
            "repos/o/r/pulls/42": _pr_payload(),
            "repos/o/r/commits/abc123/check-runs": [{"total_count": 0, "check_runs": []}],
            "repos/o/r/commits/abc123/status": [{"total_count": 0, "statuses": []}],
            "repos/o/r/git/commits/abc123": commit,
        }
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            snap = checks_rest.fetch_checks_rest("o", "r", 42)
        assert snap["HeadCommittedAt"] is None
        assert snap["PagesComplete"] is True

    def test_truncated_check_runs_mark_pages_incomplete(self):
        routes = {
            "repos/o/r/pulls/42": _pr_payload(),
            "repos/o/r/commits/abc123/check-runs": [
                {"total_count": 250, "check_runs": [{"name": "a", "status": "completed"}]}
            ],
            "repos/o/r/commits/abc123/status": [{"total_count": 0, "statuses": []}],
        }
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            assert checks_rest.fetch_checks_rest("o", "r", 42)["PagesComplete"] is False

    def test_truncated_statuses_mark_pages_incomplete(self):
        routes = {
            "repos/o/r/pulls/42": _pr_payload(),
            "repos/o/r/commits/abc123/check-runs": [{"total_count": 0, "check_runs": []}],
            "repos/o/r/commits/abc123/status": [
                {"total_count": 5, "statuses": [{"context": "c", "state": "success"}]}
            ],
        }
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            assert checks_rest.fetch_checks_rest("o", "r", 42)["PagesComplete"] is False

    def test_pr_without_head_sha_raises(self):
        routes = {"repos/o/r/pulls/42": _pr_payload(head={})}
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            with pytest.raises(RuntimeError, match="no head sha"):
                checks_rest.fetch_checks_rest("o", "r", 42)

    def test_non_object_pr_raises(self):
        with patch.object(checks_rest, "_run_gh_api", return_value=[]):
            with pytest.raises(RuntimeError, match="not an object"):
                checks_rest.fetch_checks_rest("o", "r", 42)

    def test_rest_failure_propagates_gh_text(self):
        routes = {"repos/o/r/pulls/42": RuntimeError("REST request failed: Not Found (HTTP 404)")}
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            with pytest.raises(RuntimeError, match="HTTP 404"):
                checks_rest.fetch_checks_rest("o", "r", 42)

    def test_pr_404_on_a_readable_repo_is_pull_request_not_found(self):
        routes = {"repos/o/r/pulls/42": RuntimeError("REST request failed: Not Found (HTTP 404)")}
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            with pytest.raises(checks_rest.PullRequestNotFoundError):
                checks_rest.fetch_checks_rest("o", "r", 42)

    def test_pr_404_on_an_unreadable_repo_is_not_pull_request_not_found(self):
        """A private repo the token cannot see also 404s; that is not a missing PR."""
        missing = RuntimeError("REST request failed: Not Found (HTTP 404)")
        routes = {"repos/o/r/pulls/42": missing, "repos/o/r": missing}
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            with pytest.raises(RuntimeError, match="repository o/r") as info:
                checks_rest.fetch_checks_rest("o", "r", 42)
        assert not isinstance(info.value, checks_rest.PullRequestNotFoundError)

    def test_pr_read_failure_other_than_404_does_not_probe_the_repo(self):
        routes = {
            "repos/o/r/pulls/42": RuntimeError("REST request failed: Server Error (HTTP 502)"),
            "repos/o/r": AssertionError("repo probe must not run"),
        }
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            with pytest.raises(RuntimeError, match="HTTP 502") as info:
                checks_rest.fetch_checks_rest("o", "r", 42)
        assert not isinstance(info.value, checks_rest.PullRequestNotFoundError)

    @pytest.mark.parametrize(
        ("suites", "expected"),
        [
            ({"total_count": 3, "check_suites": [{"id": 1}]}, True),
            ({"total_count": 0, "check_suites": []}, False),
            ({"check_suites": [{"id": 1}]}, True),
            ({"check_suites": []}, False),
        ],
    )
    def test_reports_whether_the_head_has_check_suites(self, suites, expected):
        """A suite with no run yet is GraphQL's empty present rollup (#2304)."""
        routes = {
            "repos/o/r/pulls/42": _pr_payload(),
            "repos/o/r/commits/abc123/check-runs": [{"total_count": 0, "check_runs": []}],
            "repos/o/r/commits/abc123/status": [{"total_count": 0, "statuses": []}],
            "repos/o/r/commits/abc123/check-suites": suites,
        }
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            snap = checks_rest.fetch_checks_rest("o", "r", 42)
        assert snap["HasCheckSuites"] is expected

    @pytest.mark.parametrize("suites", [[], "x", RuntimeError("REST request failed: boom")])
    def test_unreadable_check_suites_fail_the_fallback(self, suites):
        routes = {
            "repos/o/r/pulls/42": _pr_payload(),
            "repos/o/r/commits/abc123/check-runs": [{"total_count": 0, "check_runs": []}],
            "repos/o/r/commits/abc123/status": [{"total_count": 0, "statuses": []}],
            "repos/o/r/commits/abc123/check-suites": suites,
        }
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            with pytest.raises(RuntimeError):
                checks_rest.fetch_checks_rest("o", "r", 42)

    def test_status_endpoint_failure_is_not_swallowed(self):
        routes = {
            "repos/o/r/pulls/42": _pr_payload(),
            "repos/o/r/commits/abc123/check-runs": [{"total_count": 0, "check_runs": []}],
            "repos/o/r/commits/abc123/status": RuntimeError("REST request failed: boom"),
        }
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            with pytest.raises(RuntimeError, match="boom"):
                checks_rest.fetch_checks_rest("o", "r", 42)

    def test_snapshot_is_json_serializable(self):
        routes = {
            "repos/o/r/pulls/42": _pr_payload(),
            "repos/o/r/commits/abc123/check-runs": [{"total_count": 0, "check_runs": []}],
            "repos/o/r/commits/abc123/status": [{"total_count": 0, "statuses": []}],
        }
        with patch.object(checks_rest, "_run_gh_api", side_effect=_fake_api(routes)):
            json.dumps(checks_rest.fetch_checks_rest("o", "r", 42))


class TestMarkRequiredFromRuleset:
    def test_marks_only_names_the_ruleset_requires(self):
        checks = [{"Name": "build", "IsRequired": False}, {"Name": "lint", "IsRequired": False}]
        checks_rest.mark_required_from_ruleset(checks, ["build"])
        assert [c["IsRequired"] for c in checks] == [True, False]

    def test_clears_a_stale_true_flag(self):
        checks = [{"Name": "lint", "IsRequired": True}]
        checks_rest.mark_required_from_ruleset(checks, ["build"])
        assert checks[0]["IsRequired"] is False

    def test_empty_ruleset_marks_nothing(self):
        checks = [{"Name": "build"}]
        checks_rest.mark_required_from_ruleset(checks, [])
        assert checks[0]["IsRequired"] is False

    def test_no_checks_is_a_no_op(self):
        checks_rest.mark_required_from_ruleset([], ["build"])
