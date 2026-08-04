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
) -> dict:
    """Build a minimal GraphQL response for why_pr_blocked."""
    return {
        "repository": {
            "pullRequest": {
                "number": 42,
                "mergeStateStatus": merge_state_status,
                "commits": {
                    "nodes": [
                        {
                            "commit": {
                                "statusCheckRollup": {
                                    "state": overall_state,
                                    "contexts": {
                                        "nodes": check_nodes or [],
                                    },
                                }
                            }
                        }
                    ]
                },
                "reviewThreads": {
                    "nodes": thread_nodes or [],
                },
            }
        }
    }


def _check_run_node(name: str, conclusion: str, *, required: bool = True) -> dict:
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": "COMPLETED",
        "conclusion": conclusion,
        "isRequired": required,
    }


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

    def test_success_beats_failure_same_name(self):
        """A SUCCESS row for a name supersedes a FAILURE row (re-run)."""
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
        assert "Validate PR" not in result["FailingRequired"]
        assert result["MissingRequired"] == []

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
        assert args.base_branch == "main"

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
