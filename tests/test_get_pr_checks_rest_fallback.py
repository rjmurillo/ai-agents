"""Tests for get_pr_checks.py REST fallback on a GraphQL rate limit (issue #6391)."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.github_core.api import RepoInfo

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(
        f"{name}_rest_fallback", _SCRIPTS_DIR / f"{name}.py"
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("get_pr_checks")
_MISSING_PR = RuntimeError("Could not resolve to a PullRequest")
_RATE_LIMITED = RuntimeError(
    "GraphQL request failed: API rate limit already exceeded for user ID 42."
)


def _run(name, status, conclusion, *, url=""):
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "detailsUrl": url,
        "checkSuite": {"workflowRun": None},
        "isRequired": False,
    }


def _snapshot(
    nodes,
    *,
    pages_complete=True,
    base="main",
    merge_state="MERGEABLE",
    status="CLEAN",
    committed_at=None,
    has_check_suites=False,
):
    return {
        "Number": 42,
        "BaseBranch": base,
        "MergeState": merge_state,
        "MergeStateStatus": status,
        "Nodes": nodes,
        "PagesComplete": pages_complete,
        "HeadCommittedAt": committed_at,
        "HasCheckSuites": has_check_suites,
    }


class TestFetchChecksFallback:
    def test_rate_limit_refusal_reads_checks_over_rest(self):
        snap = _snapshot([_run("build", "COMPLETED", "SUCCESS")])
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(_mod, "fetch_checks_rest", return_value=snap) as rest,
        ):
            data = _mod.fetch_checks("o", "r", 42)
        rest.assert_called_once_with("o", "r", 42)
        assert data["DataSource"] == "rest"
        assert data["Number"] == 42
        assert data["BaseBranch"] == "main"
        assert data["HasChecks"] is True
        assert data["AllState"] == "SUCCESS"
        assert data["ChecksIncomplete"] is False
        assert [c["Name"] for c in data["Checks"]] == ["build"]
        assert data["Checks"][0]["IsPassing"] is True

    def test_secondary_limit_wording_also_falls_back(self):
        secondary = RuntimeError(
            "GraphQL request failed: You have exceeded a secondary rate limit."
        )
        with (
            patch.object(_mod, "gh_graphql", side_effect=secondary),
            patch.object(_mod, "fetch_checks_rest", return_value=_snapshot([])) as rest,
        ):
            data = _mod.fetch_checks("o", "r", 42)
        rest.assert_called_once()
        assert data["DataSource"] == "rest"

    @pytest.mark.parametrize(
        "message",
        [
            "GraphQL request failed: internal server error",
            "GraphQL request failed: Resource not accessible by integration (HTTP 403)",
            "GraphQL request failed: Bad credentials (HTTP 401)",
        ],
    )
    def test_other_graphql_failures_do_not_touch_rest(self, message):
        with (
            patch.object(_mod, "gh_graphql", side_effect=RuntimeError(message)),
            patch.object(_mod, "fetch_checks_rest") as rest,
        ):
            data = _mod.fetch_checks("o", "r", 42)
        rest.assert_not_called()
        assert data["Error"] == "ApiError"
        assert message in data["Message"]

    def test_not_found_over_graphql_stays_not_found(self):
        with (
            patch.object(_mod, "gh_graphql", side_effect=_MISSING_PR),
            patch.object(_mod, "fetch_checks_rest") as rest,
        ):
            assert _mod.fetch_checks("o", "r", 42)["Error"] == "NotFound"
        rest.assert_not_called()

    def test_rest_failure_reports_both_errors(self):
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(
                _mod,
                "fetch_checks_rest",
                side_effect=RuntimeError("REST request failed: HTTP 500"),
            ),
        ):
            data = _mod.fetch_checks("o", "r", 42)
        assert data["Error"] == "ApiError"
        assert "rate limit already exceeded" in data["Message"]
        assert "REST fallback failed" in data["Message"]
        assert "HTTP 500" in data["Message"]

    def test_rest_404_reports_not_found(self):
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(
                _mod,
                "fetch_checks_rest",
                side_effect=_mod.PullRequestNotFoundError("Not Found (HTTP 404)"),
            ),
        ):
            data = _mod.fetch_checks("o", "r", 42)
        assert data["Error"] == "NotFound"

    def test_prefer_rest_skips_graphql_entirely(self):
        with (
            patch.object(_mod, "gh_graphql") as gql,
            patch.object(_mod, "fetch_checks_rest", return_value=_snapshot([])),
        ):
            data = _mod.fetch_checks("o", "r", 42, prefer_rest=True)
        gql.assert_not_called()
        assert data["DataSource"] == "rest"

    def test_prefer_rest_failure_has_no_graphql_prefix(self):
        with patch.object(
            _mod, "fetch_checks_rest", side_effect=RuntimeError("REST request failed: boom")
        ):
            data = _mod.fetch_checks("o", "r", 42, prefer_rest=True)
        assert data["Message"] == "REST fallback failed: REST request failed: boom"

    def test_head_commit_date_reaches_the_check_data(self):
        snap = _snapshot(
            [_run("build", "COMPLETED", "SUCCESS")], committed_at="2026-10-13T10:00:00Z"
        )
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(_mod, "fetch_checks_rest", return_value=snap),
        ):
            data = _mod.fetch_checks("o", "r", 42)
        assert data["HeadCommittedAt"] == "2026-10-13T10:00:00Z"

    def test_fresh_head_holds_an_absent_required_check_as_queued(self):
        """Issue #6389 applies on the REST path: a just-pushed head is not stranded."""
        committed = datetime.now(UTC).isoformat()
        snap = _snapshot([_run("build", "COMPLETED", "SUCCESS")], committed_at=committed)
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(_mod, "fetch_checks_rest", return_value=snap),
        ):
            data = _mod.fetch_checks("o", "r", 42)
        _mod.mark_required_from_ruleset(data["Checks"], ["build", "aggregate"])
        output = _mod.build_output(data, "o", "r", True, ["build", "aggregate"], 600)
        assert output["MissingRequiredQueued"] is True

    def test_truncated_snapshot_sets_checks_incomplete(self):
        snap = _snapshot([_run("a", "COMPLETED", "SUCCESS")], pages_complete=False)
        with patch.object(_mod, "fetch_checks_rest", return_value=snap):
            assert _mod.fetch_checks("o", "r", 42, prefer_rest=True)["ChecksIncomplete"] is True

    def test_superseded_runs_are_deduplicated(self):
        url_old = "https://github.com/o/r/actions/runs/100/job/1"
        url_new = "https://github.com/o/r/actions/runs/200/job/2"
        nodes = [
            _run("build", "COMPLETED", "FAILURE", url=url_old),
            _run("build", "COMPLETED", "SUCCESS", url=url_new),
        ]
        nodes[0]["checkSuite"] = {"workflowRun": {"databaseId": 100, "runAttempt": None}}
        nodes[1]["checkSuite"] = {"workflowRun": {"databaseId": 200, "runAttempt": None}}
        with patch.object(_mod, "fetch_checks_rest", return_value=_snapshot(nodes)):
            data = _mod.fetch_checks("o", "r", 42, prefer_rest=True)
        assert len(data["Checks"]) == 1
        assert data["Checks"][0]["IsPassing"] is True


class TestOverallState:
    @pytest.mark.parametrize(
        ("checks", "expected"),
        [
            ([], "UNKNOWN"),
            ([{"IsPassing": True}], "SUCCESS"),
            ([{"IsPassing": True}, {"IsPending": True}], "PENDING"),
            ([{"IsPending": True}, {"IsFailing": True}], "FAILURE"),
        ],
    )
    def test_failure_beats_pending_beats_success(self, checks, expected):
        assert _mod._overall_state(checks) == expected


class TestMarkRestRequired:
    def test_graphql_data_is_left_alone(self):
        checks = [{"Name": "build", "IsRequired": True}]
        data = {"Checks": checks}
        assert _mod._mark_rest_required(data, [], True, 42, None) is None
        assert checks[0]["IsRequired"] is True

    def test_rest_data_takes_required_flags_from_ruleset(self):
        checks = [{"Name": "build", "IsRequired": False}, {"Name": "lint", "IsRequired": False}]
        data = {"DataSource": "rest", "Checks": checks}
        assert _mod._mark_rest_required(data, ["build"], False, 42, None) is None
        assert [c["IsRequired"] for c in checks] == [True, False]

    def test_rest_without_ruleset_is_allowed_when_not_required_only(self):
        data = {"DataSource": "rest", "Checks": [{"Name": "build", "IsRequired": False}]}
        assert _mod._mark_rest_required(data, None, False, 42, None) is None

    def test_rest_without_ruleset_fails_closed_for_required_only(self, capsys):
        data = {"DataSource": "rest", "Checks": []}
        rc = _mod._mark_rest_required(data, None, True, 42, _mod.get_output_format("json"))
        assert rc == 3
        assert "required" in capsys.readouterr().out

    def test_rest_with_empty_ruleset_fails_closed_for_required_only(self, capsys):
        checks = [{"Name": "build", "IsRequired": False}]
        data = {"DataSource": "rest", "Checks": checks}
        rc = _mod._mark_rest_required(data, [], True, 42, _mod.get_output_format("json"))
        assert rc == 3
        out = capsys.readouterr().out
        assert "lists no required checks" in out
        assert "--base-branch" not in out

    def test_rest_with_empty_ruleset_is_allowed_when_not_required_only(self):
        checks = [{"Name": "build", "IsRequired": True}]
        data = {"DataSource": "rest", "Checks": checks}
        assert _mod._mark_rest_required(data, [], False, 42, None) is None
        assert checks[0]["IsRequired"] is False


def _graphql_ok(name="build"):
    return {
        "repository": {
            "pullRequest": {
                "number": 42,
                "baseRefName": "main",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "commits": {
                    "nodes": [
                        {
                            "commit": {
                                "statusCheckRollup": {
                                    "state": "SUCCESS",
                                    "contexts": {
                                        "nodes": [
                                            {
                                                "__typename": "CheckRun",
                                                "name": name,
                                                "status": "COMPLETED",
                                                "conclusion": "SUCCESS",
                                                "detailsUrl": "",
                                                "isRequired": True,
                                            }
                                        ]
                                    },
                                }
                            }
                        }
                    ]
                },
            }
        }
    }


@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setattr(_mod, "assert_gh_authenticated", lambda: None)
    monkeypatch.setattr(_mod, "resolve_repo_params", lambda _o, _r: RepoInfo(owner="o", repo="r"))
    monkeypatch.setattr(_mod.time, "sleep", lambda _s: None)
    monkeypatch.setattr(_mod, "fetch_ruleset_required_contexts", lambda _o, _r, _b: ["build"])


def _out(capsys):
    """Return the success payload, or the whole envelope when the run failed."""
    envelope = json.loads(capsys.readouterr().out)
    return envelope["Data"] if envelope.get("Success") else envelope


class TestRestOutputStates:
    def _rest_output(self, nodes, ruleset):
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(_mod, "fetch_checks_rest", return_value=_snapshot(nodes)),
        ):
            data = _mod.fetch_checks("o", "r", 42)
        _mod._mark_rest_required(data, ruleset, False, 42, None)
        return _mod.build_output(data, "o", "r", False, ruleset, 600)

    @pytest.mark.parametrize(
        ("status", "conclusion", "expected"),
        [("COMPLETED", "FAILURE", "FAILURE"), ("IN_PROGRESS", None, "PENDING")],
    )
    def test_all_state_reports_the_rest_rollup(self, status, conclusion, expected):
        output = self._rest_output([_run("build", status, conclusion)], ["build"])
        assert output["AllState"] == expected
        assert output["DataSource"] == "rest"
        assert output["OverallState"] == expected

    def test_required_state_is_known_when_ruleset_lists_checks(self):
        output = self._rest_output([_run("build", "COMPLETED", "SUCCESS")], ["build"])
        assert output["RequiredState"] == "SUCCESS"

    @pytest.mark.parametrize("ruleset", [[], None])
    def test_required_state_unknown_without_a_ruleset(self, ruleset):
        output = self._rest_output([_run("build", "COMPLETED", "FAILURE")], ruleset)
        assert output["RequiredState"] == "UNKNOWN"
        assert output["FailedCount"] == 1

    def test_graphql_empty_ruleset_keeps_derived_required_state(self):
        data = {"Checks": [], "HasChecks": True, "MergeState": "MERGEABLE"}
        output = _mod.build_output(data, "o", "r", False, [], 600)
        assert output["RequiredState"] == "SUCCESS"


class TestMainFallback:
    def test_graphql_success_reports_graphql_source(self, _env, capsys):
        with patch.object(_mod, "gh_graphql", return_value=_graphql_ok()):
            rc = _mod.main(["--pull-request", "42", "--output-format", "json"])
        assert rc == 0
        assert _out(capsys)["DataSource"] == "graphql"

    def test_rate_limited_graphql_reads_rest_and_marks_required(self, _env, capsys):
        snap = _snapshot(
            [_run("build", "COMPLETED", "FAILURE"), _run("lint", "COMPLETED", "SUCCESS")]
        )
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(_mod, "fetch_checks_rest", return_value=snap),
        ):
            rc = _mod.main(["--pull-request", "42", "--output-format", "json"])
        out = _out(capsys)
        assert rc == 1
        assert out["DataSource"] == "rest"
        assert out["FailedRequiredChecks"] == ["build"]
        required = {c["Name"]: c["IsRequired"] for c in out["Checks"]}
        assert required == {"build": True, "lint": False}

    def test_rest_all_passing_exits_zero(self, _env, capsys):
        snap = _snapshot([_run("build", "COMPLETED", "SUCCESS")])
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(_mod, "fetch_checks_rest", return_value=snap),
        ):
            rc = _mod.main(["--pull-request", "42", "--output-format", "json"])
        out = _out(capsys)
        assert rc == 0
        assert out["AllPassing"] is True
        assert out["MissingRequiredChecks"] == []

    def test_rest_reports_required_check_that_never_ran(self, _env, capsys, monkeypatch):
        monkeypatch.setattr(
            _mod, "fetch_ruleset_required_contexts", lambda _o, _r, _b: ["build", "ghost"]
        )
        snap = _snapshot([_run("build", "COMPLETED", "SUCCESS")])
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(_mod, "fetch_checks_rest", return_value=snap),
        ):
            rc = _mod.main(["--pull-request", "42", "--output-format", "json"])
        assert rc == 1
        assert _out(capsys)["MissingRequiredChecks"] == ["ghost"]

    def test_required_only_filters_over_rest(self, _env, capsys):
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

    def test_required_only_without_base_branch_exits_three(self, _env, capsys):
        snap = _snapshot([_run("build", "COMPLETED", "SUCCESS")])
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(_mod, "fetch_checks_rest", return_value=snap),
        ):
            rc = _mod.main(
                [
                    "--pull-request",
                    "42",
                    "--required-only",
                    "--base-branch",
                    "",
                    "--output-format",
                    "json",
                ]
            )
        assert rc == 3
        assert _out(capsys)["Success"] is False

    def test_both_transports_failing_exits_three(self, _env, capsys):
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(
                _mod, "fetch_checks_rest", side_effect=RuntimeError("REST request failed: boom")
            ),
        ):
            rc = _mod.main(["--pull-request", "42", "--output-format", "json"])
        assert rc == 3
        assert "REST fallback failed" in _out(capsys)["Error"]["Message"]

    def test_wait_stays_on_rest_after_the_first_fallback(self, _env, capsys):
        pending = _snapshot([_run("build", "IN_PROGRESS", None)])
        done = _snapshot([_run("build", "COMPLETED", "SUCCESS")])
        graphql = MagicMock(side_effect=_RATE_LIMITED)
        with (
            patch.object(_mod, "gh_graphql", graphql),
            patch.object(_mod, "fetch_checks_rest", side_effect=[pending, done]) as rest,
        ):
            rc = _mod.main(["--pull-request", "42", "--wait", "--output-format", "json"])
        out = _out(capsys)
        assert rc == 0
        assert rest.call_count == 2
        assert graphql.call_count == 1
        assert out["DataSource"] == "rest"
        assert out["PendingCount"] == 0

    def test_wait_mid_loop_rest_failure_exits_three(self, _env, capsys):
        pending = _snapshot([_run("build", "IN_PROGRESS", None)])
        with (
            patch.object(_mod, "gh_graphql", side_effect=_RATE_LIMITED),
            patch.object(
                _mod,
                "fetch_checks_rest",
                side_effect=[pending, RuntimeError("REST request failed: boom")],
            ),
        ):
            rc = _mod.main(["--pull-request", "42", "--wait", "--output-format", "json"])
        assert rc == 3

    def test_wait_switches_to_rest_when_graphql_limits_mid_loop(self, _env, capsys):
        first = _graphql_ok()
        node = first["repository"]["pullRequest"]["commits"]["nodes"][0]["commit"]
        node["statusCheckRollup"]["contexts"]["nodes"][0].update(
            {"status": "IN_PROGRESS", "conclusion": None}
        )
        done = _snapshot([_run("build", "COMPLETED", "SUCCESS")])
        with (
            patch.object(_mod, "gh_graphql", side_effect=[first, _RATE_LIMITED]),
            patch.object(_mod, "fetch_checks_rest", return_value=done),
        ):
            rc = _mod.main(["--pull-request", "42", "--wait", "--output-format", "json"])
        out = _out(capsys)
        assert rc == 0
        assert out["DataSource"] == "rest"
        assert out["Checks"][0]["IsRequired"] is True
