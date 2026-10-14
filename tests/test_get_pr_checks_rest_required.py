"""REST fallback of get_pr_checks.py: per-event runs and unproven required rows.

Covers the cases where REST cannot match GraphQL on its own: a workflow run's
event (issue #6425), checks that classic branch protection may require, and a
404 from an endpoint other than the pull request read (issue #6391).
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo
from tests.test_get_pr_checks_rest_fallback import (
    _RATE_LIMITED,
    _mod,
    _out,
    _run,
    _snapshot,
)


@pytest.fixture
def rest_env(monkeypatch):
    monkeypatch.setattr(_mod, "assert_gh_authenticated", lambda: None)
    monkeypatch.setattr(_mod, "resolve_repo_params", lambda _o, _r: RepoInfo(owner="o", repo="r"))
    monkeypatch.setattr(_mod.time, "sleep", lambda _s: None)
    monkeypatch.setattr(_mod, "fetch_ruleset_required_contexts", lambda _o, _r, _b: ["build"])


class TestRestKeepsEachEventsRun:
    """A failing pull_request run must survive a newer passing push run (issue #6425)."""

    @staticmethod
    def _routes(events):
        def _call(args):
            endpoint = args[-1].split("?")[0]
            ids = (100, 101)
            if endpoint.endswith("/pulls/42"):
                return {
                    "number": 42,
                    "head": {"sha": "abc"},
                    "base": {"ref": "main"},
                    "mergeable": True,
                    "mergeable_state": "clean",
                }
            if endpoint.endswith("/check-runs"):
                runs = [
                    {
                        "name": "Tests",
                        "status": "completed",
                        "conclusion": conclusion,
                        "details_url": f"https://github.com/o/r/actions/runs/{run_id}/job/1",
                    }
                    for run_id, conclusion in zip(ids, ("failure", "success"), strict=True)
                ]
                return [{"total_count": 2, "check_runs": runs}]
            if endpoint.endswith("/status"):
                return [{"total_count": 0, "statuses": []}]
            if endpoint.endswith("/actions/runs"):
                runs = [
                    {"id": run_id, "event": event, "run_attempt": 1}
                    for run_id, event in zip(ids, events, strict=True)
                ]
                return [{"total_count": 2, "workflow_runs": runs}]
            return {"committer": {"date": "2026-10-13T10:00:00Z"}}

        return _call

    def _fetch(self, events):
        rest_module = sys.modules[_mod.fetch_checks_rest.__module__]
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(rest_module, "_run_gh_api", side_effect=self._routes(events)),
        ):
            return _mod.fetch_checks("o", "r", 42)

    def test_failing_pull_request_run_beats_newer_passing_push_run(self):
        data = self._fetch(("pull_request", "push"))
        assert [(c["Name"], c["IsFailing"]) for c in data["Checks"]] == [("Tests", True)]
        assert data["AllState"] == "FAILURE"

    def test_required_state_and_exit_code_fail_closed_for_the_hidden_run(self):
        data = self._fetch(("pull_request", "push"))
        _mod._mark_rest_required(data, ["Tests"], False, 42, None)
        output = _mod.build_output(data, "o", "r", False, ["Tests"], 600)
        assert output["RequiredState"] == "FAILURE"
        assert output["AllPassing"] is False
        assert _mod._exit_code(output, False, False) == 1

    def test_same_event_rerun_still_replaces_the_stale_failure(self):
        data = self._fetch(("push", "push"))
        assert [(c["Name"], c["IsPassing"]) for c in data["Checks"]] == [("Tests", True)]


def _norm(name, *, is_required, passing=False, failing=False):
    return {
        "Name": name,
        "Type": "CheckRun",
        "State": "COMPLETED",
        "Conclusion": "SUCCESS" if passing else "FAILURE",
        "DetailsUrl": "",
        "IsRequired": is_required,
        "IsPending": False,
        "IsPassing": passing,
        "IsFailing": failing,
    }


class TestRestRequiredState:
    def _rest_output(self, nodes, ruleset):
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(_mod, "fetch_checks_rest", return_value=_snapshot(nodes)),
        ):
            data = _mod.fetch_checks("o", "r", 42)
        _mod._mark_rest_required(data, ruleset, False, 42, None)
        return _mod.build_output(data, "o", "r", False, ruleset, 600)

    @pytest.mark.parametrize(
        ("status", "conclusion"), [("COMPLETED", "FAILURE"), ("IN_PROGRESS", None)]
    )
    def test_required_state_unknown_when_an_unlisted_row_is_red_or_running(
        self, status, conclusion
    ):
        output = self._rest_output(
            [_run("build", "COMPLETED", "SUCCESS"), _run("lint", status, conclusion)], ["build"]
        )
        assert output["RequiredState"] == "UNKNOWN"

    def test_required_state_stays_success_when_unlisted_rows_pass(self):
        output = self._rest_output(
            [_run("build", "COMPLETED", "SUCCESS"), _run("lint", "COMPLETED", "SUCCESS")],
            ["build"],
        )
        assert output["RequiredState"] == "SUCCESS"

    def test_required_state_failure_is_not_softened_by_an_unlisted_red_row(self):
        output = self._rest_output(
            [_run("build", "COMPLETED", "FAILURE"), _run("lint", "COMPLETED", "FAILURE")],
            ["build"],
        )
        assert output["RequiredState"] == "FAILURE"

    def test_graphql_unrequired_failure_keeps_required_state_success(self):
        data = {
            "Checks": [
                _norm("build", is_required=True, passing=True),
                _norm("lint", is_required=False, failing=True),
            ],
            "HasChecks": True,
            "MergeState": "MERGEABLE",
        }
        output = _mod.build_output(data, "o", "r", True, ["build"], 600)
        assert output["RequiredState"] == "SUCCESS"
        assert [c["Name"] for c in output["Checks"]] == ["build"]


class TestRestRequiredOnly:
    def test_required_only_filters_passing_unrequired_rows_over_rest(self, rest_env, capsys):
        snap = _snapshot(
            [_run("build", "COMPLETED", "SUCCESS"), _run("lint", "COMPLETED", "SUCCESS")]
        )
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(_mod, "fetch_checks_rest", return_value=snap),
        ):
            rc = _mod.main(["--pull-request", "42", "--required-only", "--output-format", "json"])
        out = _out(capsys)
        assert rc == 0
        assert [c["Name"] for c in out["Checks"]] == ["build"]
        assert out["RequiredState"] == "SUCCESS"

    def test_required_only_keeps_a_failing_row_the_ruleset_cannot_vouch_for(self, rest_env, capsys):
        # "lint" may be required by classic branch protection, which REST cannot
        # read. Dropping it would report a green gate while a required check fails.
        snap = _snapshot(
            [_run("build", "COMPLETED", "SUCCESS"), _run("lint", "COMPLETED", "FAILURE")]
        )
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(_mod, "fetch_checks_rest", return_value=snap),
        ):
            rc = _mod.main(["--pull-request", "42", "--required-only", "--output-format", "json"])
        out = _out(capsys)
        assert rc == 1
        assert {c["Name"] for c in out["Checks"]} == {"build", "lint"}
        assert out["RequiredState"] == "UNKNOWN"
        assert out["AllPassing"] is False

    def test_required_only_keeps_a_pending_row_the_ruleset_cannot_vouch_for(self, rest_env, capsys):
        snap = _snapshot([_run("build", "COMPLETED", "SUCCESS"), _run("lint", "IN_PROGRESS", None)])
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(_mod, "fetch_checks_rest", return_value=snap),
        ):
            _mod.main(["--pull-request", "42", "--required-only", "--output-format", "json"])
        out = _out(capsys)
        assert {c["Name"] for c in out["Checks"]} == {"build", "lint"}
        assert out["RequiredState"] == "UNKNOWN"
        assert out["AllPassing"] is False


class TestRestSecondaryNotFound:
    def test_secondary_rest_404_reports_api_error_not_missing_pr(self):
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(
                _mod,
                "fetch_checks_rest",
                side_effect=RuntimeError("REST request failed: Not Found (HTTP 404)"),
            ),
        ):
            data = _mod.fetch_checks("o", "r", 42)
        assert data["Error"] == "ApiError"
        assert "REST fallback failed" in data["Message"]
