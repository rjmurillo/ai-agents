# taste-lint: ignore file-size, one suite shares CLI fixtures across all gate states.
"""Tests for why_pr_blocked.py skill script (issue #4393)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[3]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
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
) -> dict:
    """Build a minimal GraphQL response for why_pr_blocked."""
    return {
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
                                        "pageInfo": context_page_info or {
                                            "hasNextPage": False,
                                            "endCursor": None,
                                        },
                                    },
                                }
                            }
                        }
                    ]
                },
                "reviewThreads": {
                    "nodes": thread_nodes or [],
                    "pageInfo": thread_page_info or {
                        "hasNextPage": False,
                        "endCursor": None,
                    },
                },
            }
        }
    }


def _check_run_node(
    name: str,
    conclusion: str,
    *,
    required: bool = True,
    run_number: int | None = None,
    run_attempt: int = 1,
    status: str = "COMPLETED",
) -> dict:
    node = {
        "__typename": "CheckRun",
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "isRequired": required,
    }
    if run_number is not None:
        node["detailsUrl"] = (
            f"https://github.com/o/r/actions/runs/{run_number}/job/{run_number}"
        )
        node["checkSuite"] = {
            "workflowRun": {
                "databaseId": run_number,
                "runAttempt": run_attempt,
            }
        }
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
            "CheckNodes": [
                _check_run_node("Validate PR", "SUCCESS", required=False)
            ],
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
            _check_run_node(
                "Validate PR", "FAILURE", required=True, run_number=100
            ),
            _check_run_node(
                "Validate PR", "SKIPPED", required=True, run_number=100
            ),
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
            check_nodes=[
                _check_run_node(
                    "Validate PR", "SUCCESS", required=True, run_number=100
                )
            ],
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
        args = build_parser().parse_args([
            "--pull-request", "42", "--base-branch", "develop",
        ])
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
        with patch("why_pr_blocked.assert_gh_authenticated"), patch(
            "why_pr_blocked.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch("why_pr_blocked.gh_graphql", return_value=gql), patch(
            "why_pr_blocked.fetch_ruleset_required_contexts",
            return_value=["Validate PR"],
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
        with patch("why_pr_blocked.assert_gh_authenticated"), patch(
            "why_pr_blocked.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch("why_pr_blocked.gh_graphql", return_value=gql), patch(
            "why_pr_blocked.fetch_ruleset_required_contexts",
            return_value=["Run Python Tests", "Validate PR"],
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])

        assert rc == 1
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["HasBlocker"] is True
        assert "Validate PR" in data["MissingRequired"]

    def test_failing_required_exits_1(self, capsys):
        gql = _gql_pr(
            merge_state_status="BLOCKED",
            overall_state="FAILURE",
            check_nodes=[_check_run_node("Validate PR", "FAILURE", required=True)],
        )
        with patch("why_pr_blocked.assert_gh_authenticated"), patch(
            "why_pr_blocked.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch("why_pr_blocked.gh_graphql", return_value=gql), patch(
            "why_pr_blocked.fetch_ruleset_required_contexts",
            return_value=["Validate PR"],
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])

        assert rc == 1
        data = json.loads(capsys.readouterr().out)["Data"]
        assert "Validate PR" in data["FailingRequired"]

    def test_pending_required_exits_2(self, capsys):
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
        with patch("why_pr_blocked.assert_gh_authenticated"), patch(
            "why_pr_blocked.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch("why_pr_blocked.gh_graphql", return_value=gql), patch(
            "why_pr_blocked.fetch_ruleset_required_contexts",
            return_value=["Validate PR"],
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])

        assert rc == 2
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["HasBlocker"] is True
        assert data["PendingRequired"] == ["Validate PR"]

    def test_unresolved_threads_exits_1(self, capsys):
        gql = _gql_pr(
            merge_state_status="BLOCKED",
            overall_state="SUCCESS",
            thread_nodes=[_thread(False), _thread(False)],
        )
        with patch("why_pr_blocked.assert_gh_authenticated"), patch(
            "why_pr_blocked.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch("why_pr_blocked.gh_graphql", return_value=gql), patch(
            "why_pr_blocked.fetch_ruleset_required_contexts", return_value=[],
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
        with patch("why_pr_blocked.assert_gh_authenticated"), patch(
            "why_pr_blocked.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch("why_pr_blocked.gh_graphql", return_value=gql), patch(
            "why_pr_blocked.fetch_ruleset_required_contexts",
            return_value=["Validate PR"],
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
        with patch("why_pr_blocked.assert_gh_authenticated"), patch(
            "why_pr_blocked.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch("why_pr_blocked.gh_graphql", return_value=gql), patch(
            "why_pr_blocked.fetch_ruleset_required_contexts",
            return_value=["Release Validation"],
        ) as mock_fetch:
            rc = main(["--pull-request", "42", "--output-format", "json"])

        assert rc == 0
        mock_fetch.assert_called_once_with("o", "r", "release/1.0")
        assert json.loads(capsys.readouterr().out)["Data"]["BaseBranch"] == "release/1.0"

    def test_pr_not_found_exits_2(self, capsys):
        gql = {"repository": {"pullRequest": None}}
        with patch("why_pr_blocked.assert_gh_authenticated"), patch(
            "why_pr_blocked.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch("why_pr_blocked.gh_graphql", return_value=gql), patch(
            "why_pr_blocked.fetch_ruleset_required_contexts", return_value=None
        ):
            rc = main(["--pull-request", "9999", "--output-format", "json"])

        assert rc == 2

    def test_api_error_exits_3(self, capsys):
        with patch("why_pr_blocked.assert_gh_authenticated"), patch(
            "why_pr_blocked.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "why_pr_blocked.gh_graphql",
            side_effect=RuntimeError("server error"),
        ), patch(
            "why_pr_blocked.fetch_ruleset_required_contexts", return_value=None
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])

        assert rc == 3

    def test_ruleset_api_error_exits_3(self, capsys):
        gql = _gql_pr(
            merge_state_status="BLOCKED",
            overall_state="SUCCESS",
            check_nodes=[_check_run_node("Validate PR", "SUCCESS")],
        )
        with patch("why_pr_blocked.assert_gh_authenticated"), patch(
            "why_pr_blocked.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch("why_pr_blocked.gh_graphql", return_value=gql), patch(
            "why_pr_blocked.fetch_ruleset_required_contexts",
            return_value=None,
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
        with patch("why_pr_blocked.assert_gh_authenticated"), patch(
            "why_pr_blocked.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch("why_pr_blocked.gh_graphql", return_value=gql), patch(
            "why_pr_blocked.fetch_ruleset_required_contexts"
        ) as mock_fetch:
            rc = main([
                "--pull-request", "42",
                "--base-branch", "",
                "--output-format", "json",
            ])

        mock_fetch.assert_not_called()
        data = json.loads(capsys.readouterr().out)["Data"]
        assert rc == 0
        assert data["MissingRequired"] == []

    def test_human_output_no_blocker_says_mergeable(self, capsys):
        gql = _gql_pr(overall_state="SUCCESS")
        with patch("why_pr_blocked.assert_gh_authenticated"), patch(
            "why_pr_blocked.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch("why_pr_blocked.gh_graphql", return_value=gql), patch(
            "why_pr_blocked.fetch_ruleset_required_contexts", return_value=[],
        ):
            rc = main(["--pull-request", "42", "--output-format", "human"])

        out = capsys.readouterr().out
        assert rc == 0
        assert "mergeable" in out.lower() or "no blocking" in out.lower()
