# taste-lint: ignore file-size, one suite shares CLI fixtures across all gate states.
"""Tests for why_pr_blocked.py skill script (issue #4393)."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[3] / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("why_pr_blocked")
main = _mod.main
build_parser = _mod.build_parser
diagnose = _mod.diagnose
fetch_pr_data = _mod.fetch_pr_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gql_pr(
    *,
    merge_state_status: str = "BLOCKED",
    overall_state: str = "FAILURE",
    check_nodes: list[dict] | None = None,
    thread_nodes: list[dict] | None = None,
    context_page_info: dict | None = None,
    thread_page_info: dict | None = None,
    base_branch: str = "main",
    committed_date: str | None = None,
) -> dict:
    """Build a minimal GraphQL response for why_pr_blocked."""
    response: dict = {
        "repository": {
            "pullRequest": {
                "number": 42,
                "baseRefName": base_branch,
                "mergeStateStatus": merge_state_status,
                "commits": {
                    "nodes": [
                        {
                            "commit": {
                                "oid": "abc123",
                                "statusCheckRollup": {
                                    "state": overall_state,
                                    "contexts": {
                                        "nodes": check_nodes or [],
                                        "pageInfo": context_page_info
                                        or {
                                            "hasNextPage": False,
                                            "endCursor": None,
                                        },
                                    },
                                },
                            }
                        }
                    ]
                },
                "reviewThreads": {
                    "nodes": thread_nodes or [],
                    "pageInfo": thread_page_info
                    or {
                        "hasNextPage": False,
                        "endCursor": None,
                    },
                },
            }
        }
    }

    if committed_date is not None:
        commit = response["repository"]["pullRequest"]["commits"]["nodes"][0]["commit"]
        commit["committedDate"] = committed_date
    return response


def _check_run_node(
    name: str,
    conclusion: str,
    *,
    required: bool = True,
    run_number: int | None = None,
    run_attempt: int = 1,
    status: str = "COMPLETED",
    event: str | None = None,
) -> dict:
    node: dict = {
        "__typename": "CheckRun",
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "isRequired": required,
    }
    if run_number is not None:
        workflow_run: dict = {"databaseId": run_number, "runAttempt": run_attempt}
        if event is not None:
            workflow_run["event"] = event
        node["detailsUrl"] = f"https://github.com/o/r/actions/runs/{run_number}/job/{run_number}"
        node["checkSuite"] = {"workflowRun": workflow_run}
    return node


def _thread(resolved: bool = False, outdated: bool = False) -> dict:
    return {"isResolved": resolved, "isOutdated": outdated}


# ---------------------------------------------------------------------------
# Tests: diagnose()
# ---------------------------------------------------------------------------


class TestDiagnose:
    def test_no_blockers_returns_all_zero(self):
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "SUCCESS",
            "CheckNodes": [_check_run_node("Validate PR", "SUCCESS")],
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Validate PR"])
        assert result["MissingRequired"] == []
        assert result["FailingRequired"] == []
        assert result["UnresolvedThreads"] == 0

    def test_missing_required_detected(self):
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "SUCCESS",
            "CheckNodes": [_check_run_node("Run Python Tests", "SUCCESS")],
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Run Python Tests", "Validate PR", "PR Validation"])
        assert set(result["MissingRequired"]) == {"Validate PR", "PR Validation"}

    def test_non_required_same_name_remains_missing(self):
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "SUCCESS",
            "CheckNodes": [_check_run_node("Validate PR", "SUCCESS", required=False)],
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Validate PR"])
        assert result["MissingRequired"] == ["Validate PR"]

    def test_failing_required_detected(self):
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "FAILURE",
            "CheckNodes": [_check_run_node("Validate PR", "FAILURE", required=True)],
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Validate PR"])
        assert "Validate PR" in result["FailingRequired"]
        assert result["MissingRequired"] == []

    def test_required_skipped_check_is_passing(self):
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "SUCCESS",
            "CheckNodes": [_check_run_node("Validate PR", "SKIPPED", required=True)],
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Validate PR"])
        assert "Validate PR" not in result["FailingRequired"]
        assert result["MissingRequired"] == []

    def test_failure_and_skipped_same_name_still_fails(self):
        nodes = [
            _check_run_node("Validate PR", "FAILURE", required=True, run_number=100),
            _check_run_node("Validate PR", "SKIPPED", required=True, run_number=100),
        ]
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "FAILURE",
            "CheckNodes": nodes,
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Validate PR"])
        assert "Validate PR" in result["FailingRequired"]
        assert result["MissingRequired"] == []

    def test_unresolved_threads_counted(self):
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "SUCCESS",
            "CheckNodes": [],
            "ThreadNodes": [_thread(False), _thread(True), _thread(False, outdated=True)],
        }
        result = diagnose(pr_data, [])
        # resolved=True and outdated=True are not unresolved
        assert result["UnresolvedThreads"] == 1

    def test_unknown_provenance_conflict_fails_closed(self):
        nodes = [
            _check_run_node("Validate PR", "FAILURE", required=True),
            _check_run_node("Validate PR", "SUCCESS", required=True),
        ]
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "SUCCESS",
            "CheckNodes": nodes,
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Validate PR"])
        assert "Validate PR" in result["FailingRequired"]
        assert result["MissingRequired"] == []

    def test_failing_check_run_beats_passing_status_context(self):
        nodes = [
            {
                "__typename": "StatusContext",
                "context": "Validate PR",
                "state": "SUCCESS",
                "isRequired": True,
            },
            _check_run_node("Validate PR", "FAILURE", required=True),
        ]
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "FAILURE",
            "CheckNodes": nodes,
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Validate PR"])
        assert result["FailingRequired"] == ["Validate PR"]

    def test_latest_failure_beats_stale_success_same_name(self):
        nodes = [
            _check_run_node("Validate PR", "SUCCESS", required=True, run_number=100),
            _check_run_node("Validate PR", "FAILURE", required=True, run_number=101),
        ]
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "FAILURE",
            "CheckNodes": nodes,
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Validate PR"])
        assert result["FailingRequired"] == ["Validate PR"]

    def test_newer_non_required_run_cannot_hide_required_failure(self):
        nodes = [
            _check_run_node(
                "Validate PR",
                "FAILURE",
                required=True,
                run_number=100,
            ),
            _check_run_node(
                "Validate PR",
                "SUCCESS",
                required=False,
                run_number=101,
            ),
        ]
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "FAILURE",
            "CheckNodes": nodes,
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Validate PR"])
        assert result["FailingRequired"] == ["Validate PR"]

    def test_latest_pending_run_is_a_blocker(self):
        nodes = [
            _check_run_node("Validate PR", "FAILURE", run_number=100),
            _check_run_node(
                "Validate PR",
                "",
                run_number=101,
                status="IN_PROGRESS",
            ),
        ]
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "PENDING",
            "CheckNodes": nodes,
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Validate PR"])
        assert result["FailingRequired"] == []
        assert result["PendingRequired"] == ["Validate PR"]

    def test_later_attempt_success_beats_earlier_attempt_failure(self):
        nodes = [
            _check_run_node(
                "Validate PR",
                "FAILURE",
                run_number=500,
                run_attempt=1,
            ),
            _check_run_node(
                "Validate PR",
                "SUCCESS",
                run_number=500,
                run_attempt=2,
            ),
        ]
        pr_data = {
            "MergeStateStatus": "CLEAN",
            "OverallState": "SUCCESS",
            "CheckNodes": nodes,
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Validate PR"])
        assert result["FailingRequired"] == []
        assert result["PendingRequired"] == []

    def test_older_push_failure_not_hidden_by_newer_pull_request_success(self):
        nodes = [
            _check_run_node("Run Python Tests", "FAILURE", run_number=100, event="push"),
            _check_run_node("Run Python Tests", "SUCCESS", run_number=101, event="pull_request"),
        ]
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "FAILURE",
            "CheckNodes": nodes,
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Run Python Tests"])
        assert result["FailingRequired"] == ["Run Python Tests"]
        assert result["BlockingRuns"] == {
            "Run Python Tests": [
                {"RunId": 100, "Attempt": 1, "Event": "push", "State": "failing"},
            ]
        }

    def test_older_pull_request_pending_not_hidden_by_newer_push_success(self):
        nodes = [
            _check_run_node(
                "Run Python Tests",
                "",
                run_number=100,
                status="IN_PROGRESS",
                event="pull_request",
            ),
            _check_run_node("Run Python Tests", "SUCCESS", run_number=101, event="push"),
        ]
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "PENDING",
            "CheckNodes": nodes,
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Run Python Tests"])
        assert result["PendingRequired"] == ["Run Python Tests"]
        assert result["BlockingRuns"]["Run Python Tests"][0]["Event"] == "pull_request"

    def test_cancelled_run_of_other_event_keeps_check_blocked_and_is_named(self):
        nodes = [
            _check_run_node("Run Python Tests", "CANCELLED", run_number=100, event="push"),
            _check_run_node("Run Python Tests", "SUCCESS", run_number=101, event="pull_request"),
        ]
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "FAILURE",
            "CheckNodes": nodes,
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Run Python Tests"])
        assert result["FailingRequired"] == ["Run Python Tests"]
        assert result["BlockingRuns"]["Run Python Tests"][0]["RunId"] == 100

    def test_rerun_within_one_event_still_supersedes_stale_failure(self):
        nodes = [
            _check_run_node("Run Python Tests", "FAILURE", run_number=100, event="push"),
            _check_run_node("Run Python Tests", "SUCCESS", run_number=102, event="push"),
            _check_run_node("Run Python Tests", "SUCCESS", run_number=101, event="pull_request"),
        ]
        pr_data = {
            "MergeStateStatus": "CLEAN",
            "OverallState": "SUCCESS",
            "CheckNodes": nodes,
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Run Python Tests"])
        assert result["FailingRequired"] == []
        assert result["PendingRequired"] == []
        assert result["BlockingRuns"] == {}

    def test_runs_without_event_keep_latest_run_precedence(self):
        nodes = [
            _check_run_node("Run Python Tests", "FAILURE", run_number=100),
            _check_run_node("Run Python Tests", "SUCCESS", run_number=101),
        ]
        pr_data = {
            "MergeStateStatus": "CLEAN",
            "OverallState": "SUCCESS",
            "CheckNodes": nodes,
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ["Run Python Tests"])
        assert result["FailingRequired"] == []

    def test_fetch_requests_workflow_event(self):
        gql = _gql_pr(check_nodes=[])
        with patch("why_pr_blocked.gh_graphql", return_value=gql) as mock_graphql:
            fetch_pr_data("o", "r", 42)
        assert "event" in mock_graphql.call_args.args[0]

    def test_fetch_preserves_run_identity_for_latest_result(self):
        nodes = [
            _check_run_node("Validate PR", "SUCCESS", required=True, run_number=100),
            _check_run_node("Validate PR", "FAILURE", required=True, run_number=101),
        ]
        gql = _gql_pr(
            merge_state_status="BLOCKED",
            overall_state="FAILURE",
            check_nodes=nodes,
        )
        with patch("why_pr_blocked.gh_graphql", return_value=gql) as mock_graphql:
            pr_data = fetch_pr_data("o", "r", 42)

        assert "detailsUrl" in mock_graphql.call_args.args[0]
        result = diagnose(pr_data, ["Validate PR"])
        assert result["FailingRequired"] == ["Validate PR"]

    def test_fetch_paginates_checks_before_diagnosis(self):
        initial = _gql_pr(
            merge_state_status="BLOCKED",
            overall_state="FAILURE",
            check_nodes=[_check_run_node("Validate PR", "SUCCESS", required=True, run_number=100)],
            context_page_info={"hasNextPage": True, "endCursor": "checks-1"},
        )
        next_page = {
            "repository": {
                "object": {
                    "statusCheckRollup": {
                        "contexts": {
                            "nodes": [
                                _check_run_node(
                                    "Validate PR",
                                    "FAILURE",
                                    required=True,
                                    run_number=101,
                                )
                            ],
                            "pageInfo": {
                                "hasNextPage": False,
                                "endCursor": None,
                            },
                        }
                    }
                }
            }
        }
        with patch(
            "why_pr_blocked.gh_graphql",
            side_effect=[initial, next_page],
        ):
            pr_data = fetch_pr_data("o", "r", 42)

        result = diagnose(pr_data, ["Validate PR"])
        assert result["FailingRequired"] == ["Validate PR"]

    def test_fetch_paginates_review_threads_before_diagnosis(self):
        initial = _gql_pr(
            merge_state_status="BLOCKED",
            overall_state="SUCCESS",
            thread_nodes=[_thread(True) for _ in range(100)],
            thread_page_info={"hasNextPage": True, "endCursor": "threads-1"},
        )
        next_page = {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [_thread(False)],
                        "pageInfo": {
                            "hasNextPage": False,
                            "endCursor": None,
                        },
                    }
                }
            }
        }
        with patch(
            "why_pr_blocked.gh_graphql",
            side_effect=[initial, next_page],
        ):
            pr_data = fetch_pr_data("o", "r", 42)

        result = diagnose(pr_data, [])
        assert result["UnresolvedThreads"] == 1

    def test_fetch_fails_closed_on_repeated_thread_cursor(self):
        initial = _gql_pr(
            thread_page_info={"hasNextPage": True, "endCursor": "threads-1"},
        )
        repeated_page = {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [],
                        "pageInfo": {
                            "hasNextPage": True,
                            "endCursor": "threads-1",
                        },
                    }
                }
            }
        }
        with patch(
            "why_pr_blocked.gh_graphql",
            side_effect=[initial, repeated_page],
        ):
            result = fetch_pr_data("o", "r", 42)

        assert result["Error"] == "ApiError"
        assert result["Message"] == "Review-thread pagination did not complete"

    def test_missing_required_none_when_ruleset_unavailable(self):
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "SUCCESS",
            "CheckNodes": [],
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, ruleset_contexts=None)
        assert result["MissingRequired"] == []
        assert result["RulesetContextsAvailable"] is False

    def test_non_required_failing_checks_not_reported(self):
        """Only required checks appear in FailingRequired."""
        pr_data = {
            "MergeStateStatus": "BLOCKED",
            "OverallState": "FAILURE",
            "CheckNodes": [_check_run_node("Optional Check", "FAILURE", required=False)],
            "ThreadNodes": [],
        }
        result = diagnose(pr_data, [])
        assert result["FailingRequired"] == []


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_requires_pull_request(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_valid_args(self):
        args = build_parser().parse_args(["--pull-request", "42"])
        assert args.pull_request == 42
        assert args.base_branch is None

    def test_custom_base_branch(self):
        args = build_parser().parse_args(
            [
                "--pull-request",
                "42",
                "--base-branch",
                "develop",
            ]
        )
        assert args.base_branch == "develop"


# ---------------------------------------------------------------------------
# Tests: main() / CLI integration
# ---------------------------------------------------------------------------


class TestMain:
    def _patch_env(self, gql_data, *, ruleset=None):
        return (
            patch("why_pr_blocked.assert_gh_authenticated"),
            patch(
                "why_pr_blocked.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("why_pr_blocked.gh_graphql", return_value=gql_data),
            patch(
                "why_pr_blocked.fetch_ruleset_required_contexts",
                return_value=ruleset,
            ),
        )

    def test_no_blocker_exits_0(self, capsys):
        gql = _gql_pr(
            merge_state_status="BLOCKED",
            overall_state="SUCCESS",
            check_nodes=[_check_run_node("Validate PR", "SUCCESS")],
        )
        with (
            patch("why_pr_blocked.assert_gh_authenticated"),
            patch(
                "why_pr_blocked.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("why_pr_blocked.gh_graphql", return_value=gql),
            patch(
                "why_pr_blocked.fetch_ruleset_required_contexts",
                return_value=["Validate PR"],
            ),
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])

        assert rc == 0
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["HasBlocker"] is False
        assert data["MissingRequired"] == []
        assert data["FailingRequired"] == []
        assert data["UnresolvedThreads"] == 0

    def test_missing_required_exits_1(self, capsys):
        gql = _gql_pr(
            merge_state_status="BLOCKED",
            overall_state="SUCCESS",
            check_nodes=[_check_run_node("Run Python Tests", "SUCCESS")],
        )
        with (
            patch("why_pr_blocked.assert_gh_authenticated"),
            patch(
                "why_pr_blocked.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("why_pr_blocked.gh_graphql", return_value=gql),
            patch(
                "why_pr_blocked.fetch_ruleset_required_contexts",
                return_value=["Run Python Tests", "Validate PR"],
            ),
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])

        assert rc == 1
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["HasBlocker"] is True
        assert "Validate PR" in data["MissingRequired"]

    def _human_output(self, check_nodes, ruleset, capsys):
        gql = _gql_pr(
            merge_state_status="BLOCKED",
            overall_state="SUCCESS",
            check_nodes=check_nodes,
        )
        with (
            patch("why_pr_blocked.assert_gh_authenticated"),
            patch(
                "why_pr_blocked.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("why_pr_blocked.gh_graphql", return_value=gql),
            patch(
                "why_pr_blocked.fetch_ruleset_required_contexts",
                return_value=ruleset,
            ),
        ):
            rc = main(["--pull-request", "42", "--output-format", "human"])
        captured = capsys.readouterr()
        return rc, captured.out + captured.err

    def test_missing_required_human_summary_includes_recovery_hint(self, capsys):
        """Issue #5162: the blocked summary names close/reopen for missing checks."""
        rc, text = self._human_output(
            [_check_run_node("Run Python Tests", "SUCCESS")],
            ["Run Python Tests", "Validate PR"],
            capsys,
        )

        assert rc == 1
        assert "1 missing required check(s)" in text
        assert "close and reopen the PR" in text
        assert "Required check never reported" in text

    def test_no_missing_checks_has_no_recovery_hint(self, capsys):
        """Negative control: a blocker other than a missing check carries no hint."""
        rc, text = self._human_output(
            [
                _check_run_node("Run Python Tests", "SUCCESS"),
                _check_run_node("Validate PR", "FAILURE"),
            ],
            ["Run Python Tests", "Validate PR"],
            capsys,
        )

        assert rc == 1
        assert "failing required check(s)" in text
        assert "close and reopen" not in text

    def test_cross_event_failure_exits_1_and_names_run_and_event(self, capsys):
        """Issue #6408: a red push run behind a green pull_request run blocks."""
        rc, text = self._human_output(
            [
                _check_run_node("Run Python Tests", "FAILURE", run_number=100, event="push"),
                _check_run_node(
                    "Run Python Tests", "SUCCESS", run_number=101, event="pull_request"
                ),
            ],
            ["Run Python Tests"],
            capsys,
        )

        assert rc == 1
        assert "1 failing required check(s)" in text
        assert "Rerun: Run Python Tests (run 100, push)" in text

    def test_same_event_rerun_success_exits_0_without_rerun_hint(self, capsys):
        """Negative control: a rerun of the same event clears the stale failure."""
        rc, text = self._human_output(
            [
                _check_run_node("Run Python Tests", "FAILURE", run_number=100, event="push"),
                _check_run_node("Run Python Tests", "SUCCESS", run_number=101, event="push"),
            ],
            ["Run Python Tests"],
            capsys,
        )

        assert rc == 0
        assert "Rerun:" not in text

    def test_failing_required_exits_1(self, capsys):
        gql = _gql_pr(
            merge_state_status="BLOCKED",
            overall_state="FAILURE",
            check_nodes=[_check_run_node("Validate PR", "FAILURE", required=True)],
        )
        with (
            patch("why_pr_blocked.assert_gh_authenticated"),
            patch(
                "why_pr_blocked.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("why_pr_blocked.gh_graphql", return_value=gql),
            patch(
                "why_pr_blocked.fetch_ruleset_required_contexts",
                return_value=["Validate PR"],
            ),
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])

        assert rc == 1
        data = json.loads(capsys.readouterr().out)["Data"]
        assert "Validate PR" in data["FailingRequired"]

    def test_pending_required_exits_1(self, capsys):
        gql = _gql_pr(
            merge_state_status="BLOCKED",
            overall_state="PENDING",
            check_nodes=[
                _check_run_node(
                    "Validate PR",
                    "",
                    required=True,
                    run_number=101,
                    status="IN_PROGRESS",
                )
            ],
        )
        with (
            patch("why_pr_blocked.assert_gh_authenticated"),
            patch(
                "why_pr_blocked.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("why_pr_blocked.gh_graphql", return_value=gql),
            patch(
                "why_pr_blocked.fetch_ruleset_required_contexts",
                return_value=["Validate PR"],
            ),
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])

        assert rc == 1
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["HasBlocker"] is True
        assert data["PendingRequired"] == ["Validate PR"]

    def test_unresolved_threads_exits_1(self, capsys):
        gql = _gql_pr(
            merge_state_status="BLOCKED",
            overall_state="SUCCESS",
            thread_nodes=[_thread(False), _thread(False)],
        )
        with (
            patch("why_pr_blocked.assert_gh_authenticated"),
            patch(
                "why_pr_blocked.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("why_pr_blocked.gh_graphql", return_value=gql),
            patch(
                "why_pr_blocked.fetch_ruleset_required_contexts",
                return_value=[],
            ),
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])

        assert rc == 1
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["UnresolvedThreads"] == 2

    def test_dirty_merge_state_exits_1(self, capsys):
        gql = _gql_pr(
            merge_state_status="DIRTY",
            overall_state="SUCCESS",
            check_nodes=[_check_run_node("Validate PR", "SUCCESS")],
        )
        with (
            patch("why_pr_blocked.assert_gh_authenticated"),
            patch(
                "why_pr_blocked.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("why_pr_blocked.gh_graphql", return_value=gql),
            patch(
                "why_pr_blocked.fetch_ruleset_required_contexts",
                return_value=["Validate PR"],
            ),
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])

        assert rc == 1
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["HasBlocker"] is True
        assert data["MergeStateStatus"] == "DIRTY"

    def test_uses_pr_base_branch_by_default(self, capsys):
        gql = _gql_pr(
            base_branch="release/1.0",
            overall_state="SUCCESS",
            check_nodes=[_check_run_node("Release Validation", "SUCCESS")],
        )
        with (
            patch("why_pr_blocked.assert_gh_authenticated"),
            patch(
                "why_pr_blocked.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("why_pr_blocked.gh_graphql", return_value=gql),
            patch(
                "why_pr_blocked.fetch_ruleset_required_contexts",
                return_value=["Release Validation"],
            ) as mock_fetch,
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])

        assert rc == 0
        mock_fetch.assert_called_once_with("o", "r", "release/1.0")
        assert json.loads(capsys.readouterr().out)["Data"]["BaseBranch"] == "release/1.0"

    def test_pr_not_found_exits_2(self, capsys):
        gql = {"repository": {"pullRequest": None}}
        with (
            patch("why_pr_blocked.assert_gh_authenticated"),
            patch(
                "why_pr_blocked.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("why_pr_blocked.gh_graphql", return_value=gql),
            patch("why_pr_blocked.fetch_ruleset_required_contexts", return_value=None),
        ):
            rc = main(["--pull-request", "9999", "--output-format", "json"])

        assert rc == 2

    def test_api_error_exits_3(self, capsys):
        with (
            patch("why_pr_blocked.assert_gh_authenticated"),
            patch(
                "why_pr_blocked.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "why_pr_blocked.gh_graphql",
                side_effect=RuntimeError("server error"),
            ),
            patch("why_pr_blocked.fetch_ruleset_required_contexts", return_value=None),
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])

        assert rc == 3

    def test_ruleset_api_error_exits_3(self, capsys):
        gql = _gql_pr(
            merge_state_status="BLOCKED",
            overall_state="SUCCESS",
            check_nodes=[_check_run_node("Validate PR", "SUCCESS")],
        )
        with (
            patch("why_pr_blocked.assert_gh_authenticated"),
            patch(
                "why_pr_blocked.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("why_pr_blocked.gh_graphql", return_value=gql),
            patch(
                "why_pr_blocked.fetch_ruleset_required_contexts",
                return_value=None,
            ),
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])

        assert rc == 3
        assert "Failed to read required checks" in capsys.readouterr().out

    def test_base_branch_empty_skips_ruleset(self, capsys):
        """--base-branch '' skips ruleset fetch; MissingRequired not populated."""
        gql = _gql_pr(
            merge_state_status="BLOCKED",
            overall_state="SUCCESS",
            check_nodes=[_check_run_node("Run Python Tests", "SUCCESS")],
        )
        with (
            patch("why_pr_blocked.assert_gh_authenticated"),
            patch(
                "why_pr_blocked.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("why_pr_blocked.gh_graphql", return_value=gql),
            patch("why_pr_blocked.fetch_ruleset_required_contexts") as mock_fetch,
        ):
            rc = main(
                [
                    "--pull-request",
                    "42",
                    "--base-branch",
                    "",
                    "--output-format",
                    "json",
                ]
            )

        mock_fetch.assert_not_called()
        data = json.loads(capsys.readouterr().out)["Data"]
        assert rc == 0
        assert data["MissingRequired"] == []

    def test_human_output_no_blocker_says_mergeable(self, capsys):
        gql = _gql_pr(overall_state="SUCCESS")
        with (
            patch("why_pr_blocked.assert_gh_authenticated"),
            patch(
                "why_pr_blocked.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("why_pr_blocked.gh_graphql", return_value=gql),
            patch(
                "why_pr_blocked.fetch_ruleset_required_contexts",
                return_value=[],
            ),
        ):
            rc = main(["--pull-request", "42", "--output-format", "human"])

        out = capsys.readouterr().out
        assert rc == 0
        assert "mergeable" in out.lower() or "no blocking" in out.lower()


class TestFetchPrDataLookupFailure:
    @pytest.mark.parametrize(
        "message",
        [
            "Could not resolve to a PullRequest with the number of 42.",
            "gh: Not Found (HTTP 404)",
        ],
    )
    def test_missing_pr_maps_to_not_found(self, message):
        with patch("why_pr_blocked.gh_graphql", side_effect=RuntimeError(message)):
            result = fetch_pr_data("o", "r", 42)
        assert result["Error"] == "NotFound"

    def test_transport_fault_maps_to_api_error(self):
        with patch(
            "why_pr_blocked.gh_graphql",
            side_effect=RuntimeError("Could not resolve host: api.github.com"),
        ):
            result = fetch_pr_data("o", "r", 42)
        assert result["Error"] == "ApiError"


# ---------------------------------------------------------------------------
# Tests: queued vs absent required checks (issue #6389)
# ---------------------------------------------------------------------------


def _committed_at(age_seconds: int) -> str:
    when = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


_RULESET = ["Run Python Tests", "Validate PR"]


class TestQueuedVsAbsent:
    def _pr(self, age_seconds):
        return {
            "BaseBranch": "main",
            "MergeStateStatus": "BLOCKED",
            "OverallState": "SUCCESS",
            "HeadCommittedAt": None if age_seconds is None else _committed_at(age_seconds),
            "CheckNodes": [_check_run_node("Run Python Tests", "SUCCESS")],
            "ThreadNodes": [],
        }

    def test_fresh_head_splits_missing_into_queued(self):
        result = diagnose(self._pr(120), _RULESET)
        assert result["MissingRequired"] == ["Validate PR"]
        assert result["QueuedRequired"] == ["Validate PR"]
        assert result["AbsentRequired"] == []

    def test_stale_head_splits_missing_into_absent(self):
        result = diagnose(self._pr(7200), _RULESET)
        assert result["MissingRequired"] == ["Validate PR"]
        assert result["QueuedRequired"] == []
        assert result["AbsentRequired"] == ["Validate PR"]

    def test_unknown_head_age_is_absent(self):
        result = diagnose(self._pr(None), _RULESET)
        assert result["QueuedRequired"] == []
        assert result["AbsentRequired"] == ["Validate PR"]

    def test_zero_grace_is_absent(self):
        result = diagnose(self._pr(120), _RULESET, 0)
        assert result["QueuedRequired"] == []
        assert result["AbsentRequired"] == ["Validate PR"]

    def test_nothing_missing_has_empty_lists(self):
        result = diagnose(self._pr(120), ["Run Python Tests"])
        assert result["QueuedRequired"] == []
        assert result["AbsentRequired"] == []

    def test_unavailable_ruleset_has_empty_lists(self):
        result = diagnose(self._pr(120), None)
        assert result["QueuedRequired"] == []
        assert result["AbsentRequired"] == []

    def test_fetch_pr_data_returns_head_committed_date(self):
        gql = _gql_pr(
            check_nodes=[_check_run_node("Run Python Tests", "SUCCESS")],
            committed_date="2026-10-12T10:00:00Z",
        )
        with patch("why_pr_blocked.gh_graphql", return_value=gql):
            data = fetch_pr_data("o", "r", 42)
        assert data["HeadCommittedAt"] == "2026-10-12T10:00:00Z"

    def test_fetch_pr_data_head_date_none_without_commits(self):
        gql = _gql_pr()
        gql["repository"]["pullRequest"]["commits"] = {"nodes": []}
        with patch("why_pr_blocked.gh_graphql", return_value=gql):
            data = fetch_pr_data("o", "r", 42)
        assert data["HeadCommittedAt"] is None

    def test_query_requests_committed_date(self):
        assert "committedDate" in _mod._PR_QUERY

    def test_parser_default_and_custom_grace(self):
        assert build_parser().parse_args(["--pull-request", "1"]).missing_grace_seconds == 2700
        args = build_parser().parse_args(["--pull-request", "1", "--missing-grace-seconds", "0"])
        assert args.missing_grace_seconds == 0

    def _run(self, age_seconds, capsys, fmt, extra=()):
        gql = _gql_pr(
            overall_state="SUCCESS",
            check_nodes=[_check_run_node("Run Python Tests", "SUCCESS")],
            committed_date=_committed_at(age_seconds),
        )
        with (
            patch("why_pr_blocked.assert_gh_authenticated"),
            patch(
                "why_pr_blocked.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("why_pr_blocked.gh_graphql", return_value=gql),
            patch("why_pr_blocked.fetch_ruleset_required_contexts", return_value=_RULESET),
        ):
            rc = main(["--pull-request", "42", "--output-format", fmt, *extra])
        captured = capsys.readouterr()
        return rc, captured.out + captured.err

    def test_fresh_head_summary_says_queued_without_reopen_hint(self, capsys):
        rc, text = self._run(120, capsys, "human")
        assert rc == 1
        assert "queued required check(s) not yet reported" in text
        assert "missing required check(s)" not in text
        assert "close and reopen the PR;" not in text

    def test_stale_head_summary_keeps_reopen_hint(self, capsys):
        rc, text = self._run(7200, capsys, "human")
        assert rc == 1
        assert "1 missing required check(s)" in text
        assert "close and reopen the PR" in text
        assert "queued required check(s)" not in text

    def test_json_lists_queued_and_absent_separately(self, capsys):
        rc, text = self._run(120, capsys, "json")
        data = json.loads(text)["Data"]
        assert rc == 1
        assert data["HasBlocker"] is True
        assert data["MissingRequired"] == ["Validate PR"]
        assert data["QueuedRequired"] == ["Validate PR"]
        assert data["AbsentRequired"] == []
        assert data["HeadCommittedAt"]

    def test_zero_grace_flag_reports_absent(self, capsys):
        rc, text = self._run(120, capsys, "json", ("--missing-grace-seconds", "0"))
        data = json.loads(text)["Data"]
        assert rc == 1
        assert data["QueuedRequired"] == []
        assert data["AbsentRequired"] == ["Validate PR"]
