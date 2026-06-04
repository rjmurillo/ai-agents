"""Tests for get_pr_checks.py skill script."""

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
    Path(__file__).resolve().parents[1]
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


_mod = _import_script("get_pr_checks")
main = _mod.main
build_parser = _mod.build_parser
normalize_check = _mod.normalize_check
fetch_checks = _mod.fetch_checks
build_output = _mod.build_output
dedupe_checks = _mod.dedupe_checks


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _check(name: str, *, passing=False, failing=False, pending=False,
           required=True, state="COMPLETED", conclusion="", details=""):
    """Build a normalized check dict for dedupe tests."""
    return {
        "Name": name,
        "Type": "CheckRun",
        "State": state,
        "Conclusion": conclusion,
        "DetailsUrl": details,
        "IsRequired": required,
        "IsPending": pending,
        "IsPassing": passing,
        "IsFailing": failing,
    }


def _check_run_node(name, status, conclusion, *, required=True):
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "detailsUrl": "",
        "isRequired": required,
    }


def _rollup_response(nodes, state="FAILURE", number=2201):
    return {
        "repository": {
            "pullRequest": {
                "number": number,
                "commits": {
                    "nodes": [
                        {"commit": {"statusCheckRollup": {
                            "state": state,
                            "contexts": {"nodes": nodes},
                        }}},
                    ],
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_valid_args(self):
        args = build_parser().parse_args(["--pull-request", "42"])
        assert args.pull_request == 42

    def test_wait_and_timeout(self):
        args = build_parser().parse_args([
            "--pull-request", "1", "--wait", "--timeout-seconds", "60",
        ])
        assert args.wait is True
        assert args.timeout_seconds == 60

    def test_output_format_default_is_auto(self):
        args = build_parser().parse_args(["--pull-request", "1"])
        assert args.output_format == "auto"

    def test_output_format_json(self):
        args = build_parser().parse_args([
            "--pull-request", "1", "--output-format", "json",
        ])
        assert args.output_format == "json"

    def test_output_format_invalid_rejected(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([
                "--pull-request", "1", "--output-format", "xml",
            ])


# ---------------------------------------------------------------------------
# Tests: normalize_check
# ---------------------------------------------------------------------------


class TestNormalizeCheck:
    def test_check_run_success(self):
        ctx = {
            "__typename": "CheckRun",
            "name": "build",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "detailsUrl": "https://example.com",
            "isRequired": True,
        }
        result = normalize_check(ctx)
        assert result["Name"] == "build"
        assert result["IsPassing"] is True
        assert result["IsFailing"] is False
        assert result["IsPending"] is False

    def test_check_run_failure(self):
        ctx = {
            "__typename": "CheckRun",
            "name": "test",
            "status": "COMPLETED",
            "conclusion": "FAILURE",
            "detailsUrl": "",
            "isRequired": False,
        }
        result = normalize_check(ctx)
        assert result["IsFailing"] is True
        assert result["IsPassing"] is False

    def test_check_run_pending(self):
        ctx = {
            "__typename": "CheckRun",
            "name": "lint",
            "status": "IN_PROGRESS",
            "conclusion": "",
            "detailsUrl": "",
            "isRequired": True,
        }
        result = normalize_check(ctx)
        assert result["IsPending"] is True

    @pytest.mark.parametrize("conclusion", ["STALE", "STARTUP_FAILURE"])
    def test_check_run_stale_and_startup_failure_are_failing(self, conclusion):
        ctx = {
            "__typename": "CheckRun",
            "name": "build",
            "status": "COMPLETED",
            "conclusion": conclusion,
            "detailsUrl": "",
            "isRequired": True,
        }
        result = normalize_check(ctx)
        assert result["IsFailing"] is True
        assert result["IsPassing"] is False

    def test_status_context(self):
        ctx = {
            "__typename": "StatusContext",
            "context": "ci/travis",
            "state": "SUCCESS",
            "targetUrl": "https://example.com",
            "isRequired": True,
        }
        result = normalize_check(ctx)
        assert result["Name"] == "ci/travis"
        assert result["IsPassing"] is True

    def test_unknown_typename_returns_none(self):
        result = normalize_check({"__typename": "Unknown"})
        assert result is None


# ---------------------------------------------------------------------------
# Tests: build_output
# ---------------------------------------------------------------------------


class TestBuildOutput:
    def test_all_passing(self):
        check_data = {
            "Number": 42,
            "HasChecks": True,
            "OverallState": "SUCCESS",
            "Checks": [
                {
                    "Name": "build", "IsPassing": True,
                    "IsFailing": False, "IsPending": False,
                    "IsRequired": True, "State": "COMPLETED",
                    "Conclusion": "SUCCESS", "DetailsUrl": "",
                },
            ],
        }
        output = build_output(check_data, "o", "r")
        assert output["AllPassing"] is True
        assert output["FailedCount"] == 0

    def test_with_failures(self):
        check_data = {
            "Number": 42,
            "HasChecks": True,
            "OverallState": "FAILURE",
            "Checks": [
                {
                    "Name": "build", "IsPassing": False,
                    "IsFailing": True, "IsPending": False,
                    "IsRequired": True, "State": "COMPLETED",
                    "Conclusion": "FAILURE", "DetailsUrl": "",
                },
            ],
        }
        output = build_output(check_data, "o", "r")
        assert output["AllPassing"] is False
        assert output["FailedCount"] == 1

    def test_required_only_filter(self):
        check_data = {
            "Number": 42,
            "HasChecks": True,
            "OverallState": "SUCCESS",
            "Checks": [
                {
                    "Name": "required", "IsPassing": True,
                    "IsFailing": False, "IsPending": False,
                    "IsRequired": True, "State": "COMPLETED",
                    "Conclusion": "SUCCESS", "DetailsUrl": "",
                },
                {
                    "Name": "optional", "IsPassing": False,
                    "IsFailing": True, "IsPending": False,
                    "IsRequired": False, "State": "COMPLETED",
                    "Conclusion": "FAILURE", "DetailsUrl": "",
                },
            ],
        }
        output = build_output(check_data, "o", "r", required_only=True)
        assert len(output["Checks"]) == 1
        assert output["Checks"][0]["Name"] == "required"


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "get_pr_checks.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_pr_not_found_returns_2(self, capsys):
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql",
            side_effect=RuntimeError("Could not resolve PR"),
        ):
            rc = main(["--pull-request", "999"])
        assert rc == 2

    def test_all_passing_returns_0(self, capsys):
        gql_data = {
            "repository": {
                "pullRequest": {
                    "number": 42,
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
                                                    "name": "build",
                                                    "status": "COMPLETED",
                                                    "conclusion": "SUCCESS",
                                                    "detailsUrl": "",
                                                    "isRequired": True,
                                                },
                                            ],
                                        },
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        }
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["AllPassing"] is True

    def test_output_format_json_suppresses_stderr(self, capsys):
        gql_data = {
            "repository": {
                "pullRequest": {
                    "number": 42,
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
                                                    "name": "build",
                                                    "status": "COMPLETED",
                                                    "conclusion": "SUCCESS",
                                                    "detailsUrl": "",
                                                    "isRequired": True,
                                                },
                                            ],
                                        },
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        }
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])
        assert rc == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        output = json.loads(captured.out)
        assert output["Data"]["AllPassing"] is True

    def test_output_format_human_includes_summary(self, capsys):
        gql_data = {
            "repository": {
                "pullRequest": {
                    "number": 42,
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
                                                    "name": "build",
                                                    "status": "COMPLETED",
                                                    "conclusion": "SUCCESS",
                                                    "detailsUrl": "",
                                                    "isRequired": True,
                                                },
                                            ],
                                        },
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        }
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42", "--output-format", "human"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "All 1 check(s) passing" in captured.out

    def test_output_format_json_suppresses_stderr_on_failure(self, capsys):
        gql_data = {
            "repository": {
                "pullRequest": {
                    "number": 42,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "statusCheckRollup": {
                                        "state": "FAILURE",
                                        "contexts": {
                                            "nodes": [
                                                {
                                                    "__typename": "CheckRun",
                                                    "name": "test",
                                                    "status": "COMPLETED",
                                                    "conclusion": "FAILURE",
                                                    "detailsUrl": "",
                                                    "isRequired": True,
                                                },
                                            ],
                                        },
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        }
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])
        assert rc == 1
        captured = capsys.readouterr()
        assert captured.err == ""
        output = json.loads(captured.out)
        assert output["Data"]["FailedCount"] == 1

    def test_failed_check_returns_1(self, capsys):
        gql_data = {
            "repository": {
                "pullRequest": {
                    "number": 42,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "statusCheckRollup": {
                                        "state": "FAILURE",
                                        "contexts": {
                                            "nodes": [
                                                {
                                                    "__typename": "CheckRun",
                                                    "name": "test",
                                                    "status": "COMPLETED",
                                                    "conclusion": "FAILURE",
                                                    "detailsUrl": "",
                                                    "isRequired": True,
                                                },
                                            ],
                                        },
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        }
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 1

    def test_api_error_returns_3(self, capsys):
        """Generic RuntimeError (not 'not found') returns exit code 3."""
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql",
            side_effect=RuntimeError("internal server error"),
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 3
        output = json.loads(capsys.readouterr().out)
        assert output["Success"] is False
        assert "internal server error" in output["Error"]["Message"]

    def test_no_commits_returns_unknown(self, capsys):
        """PR with no commits returns UNKNOWN state."""
        gql_data = {
            "repository": {
                "pullRequest": {
                    "number": 42,
                    "commits": {"nodes": []},
                },
            },
        }
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["HasChecks"] is False
        assert output["Data"]["OverallState"] == "UNKNOWN"

    def test_no_rollup_returns_unknown(self, capsys):
        """PR with no statusCheckRollup returns UNKNOWN state."""
        gql_data = {
            "repository": {
                "pullRequest": {
                    "number": 42,
                    "commits": {
                        "nodes": [{"commit": {"statusCheckRollup": None}}],
                    },
                },
            },
        }
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["HasChecks"] is False

    def test_pr_not_in_response_returns_2(self, capsys):
        """PR not found in GraphQL response returns exit code 2."""
        gql_data = {"repository": {"pullRequest": None}}
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 2
        output = json.loads(capsys.readouterr().out)
        assert output["Success"] is False

    def test_pending_checks_returns_0(self, capsys):
        """Pending checks (no --wait) return exit code 0 with pending count in output."""
        gql_data = {
            "repository": {
                "pullRequest": {
                    "number": 42,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "statusCheckRollup": {
                                        "state": "PENDING",
                                        "contexts": {
                                            "nodes": [
                                                {
                                                    "__typename": "CheckRun",
                                                    "name": "build",
                                                    "status": "IN_PROGRESS",
                                                    "conclusion": "",
                                                    "detailsUrl": "",
                                                    "isRequired": True,
                                                },
                                            ],
                                        },
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        }
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["PendingCount"] > 0

    def test_wait_timeout_returns_7(self, capsys):
        """--wait with timeout returns exit code 7."""
        gql_data = {
            "repository": {
                "pullRequest": {
                    "number": 42,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "statusCheckRollup": {
                                        "state": "PENDING",
                                        "contexts": {
                                            "nodes": [
                                                {
                                                    "__typename": "CheckRun",
                                                    "name": "build",
                                                    "status": "IN_PROGRESS",
                                                    "conclusion": "",
                                                    "detailsUrl": "",
                                                    "isRequired": True,
                                                },
                                            ],
                                        },
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        }
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ), patch(
            "get_pr_checks.time.monotonic",
            side_effect=[0.0, 999.0],
        ), patch(
            "get_pr_checks.time.sleep",
        ):
            rc = main([
                "--pull-request", "42",
                "--wait", "--timeout-seconds", "10",
                "--output-format", "human",
            ])
        assert rc == 7
        captured = capsys.readouterr()
        assert "Timeout" in captured.out

    def test_wait_timeout_json_suppresses_stderr(self, capsys):
        """--wait timeout with --output-format json suppresses stderr."""
        gql_data = {
            "repository": {
                "pullRequest": {
                    "number": 42,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "statusCheckRollup": {
                                        "state": "PENDING",
                                        "contexts": {
                                            "nodes": [
                                                {
                                                    "__typename": "CheckRun",
                                                    "name": "build",
                                                    "status": "IN_PROGRESS",
                                                    "conclusion": "",
                                                    "detailsUrl": "",
                                                    "isRequired": True,
                                                },
                                            ],
                                        },
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        }
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ), patch(
            "get_pr_checks.time.monotonic",
            side_effect=[0.0, 999.0],
        ), patch(
            "get_pr_checks.time.sleep",
        ):
            rc = main([
                "--pull-request", "42",
                "--wait", "--timeout-seconds", "10",
                "--output-format", "json",
            ])
        assert rc == 7
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_wait_transient_empty_tags_incomplete(self, capsys):
        """#2304: --wait that exhausts its budget while the rollup is empty
        returns 7 and tags ChecksIncomplete, not a premature PASS."""
        empty_gql = {
            "repository": {
                "pullRequest": {
                    "number": 42,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "statusCheckRollup": {
                                        "state": "PENDING",
                                        "contexts": {"nodes": []},
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        }
        with patch("get_pr_checks.assert_gh_authenticated"), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql", return_value=empty_gql,
        ), patch(
            "get_pr_checks.time.monotonic", side_effect=[0.0, 999.0],
        ), patch("get_pr_checks.time.sleep"):
            rc = main([
                "--pull-request", "42", "--wait",
                "--timeout-seconds", "10", "--output-format", "json",
            ])
        assert rc == 7
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["ChecksIncomplete"] is True

    def test_wait_genuine_no_checks_settles_immediately(self, capsys):
        """#2304: --wait settles missing rollups as real no-check PRs."""
        no_checks_gql = {
            "repository": {
                "pullRequest": {
                    "number": 42,
                    "commits": {"nodes": [{"commit": {"statusCheckRollup": None}}]},
                },
            },
        }
        with patch("get_pr_checks.assert_gh_authenticated"), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql", return_value=no_checks_gql,
        ), patch("get_pr_checks.time.sleep") as sleep_mock:
            rc = main([
                "--pull-request", "42", "--wait",
                "--timeout-seconds", "10", "--output-format", "json",
            ])
        assert rc == 0
        sleep_mock.assert_not_called()
        output = json.loads(capsys.readouterr().out)["Data"]
        assert output["HasChecks"] is False
        assert output["ChecksIncomplete"] is False

    def test_wait_empty_then_populated_settles(self, capsys):
        """#2304: a transient empty poll must not terminate --wait; once the
        rollup populates, the populated result wins (no false 'no checks')."""
        empty_gql = {
            "repository": {
                "pullRequest": {
                    "number": 42,
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "statusCheckRollup": {
                                        "state": "PENDING",
                                        "contexts": {"nodes": []},
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        }
        passing_gql = {
            "repository": {
                "pullRequest": {
                    "number": 42,
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
                                                    "name": "build",
                                                    "status": "COMPLETED",
                                                    "conclusion": "SUCCESS",
                                                    "detailsUrl": "",
                                                    "isRequired": True,
                                                },
                                            ],
                                        },
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        }
        with patch("get_pr_checks.assert_gh_authenticated"), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql", side_effect=[empty_gql, passing_gql],
        ), patch(
            "get_pr_checks.time.monotonic", side_effect=[0.0, 1.0],
        ), patch("get_pr_checks.time.sleep"):
            rc = main([
                "--pull-request", "42", "--wait",
                "--timeout-seconds", "60", "--output-format", "json",
            ])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)["Data"]
        assert output["ChecksIncomplete"] is False
        assert output["PassedCount"] == 1
        assert output["AllPassing"] is True

    def test_no_checks_without_wait_not_incomplete(self, capsys):
        """#2304: without --wait, an empty rollup is reported immediately as a
        genuine no-checks PR (ChecksIncomplete False), unchanged behavior."""
        empty_gql = {
            "repository": {
                "pullRequest": {
                    "number": 42,
                    "commits": {"nodes": [{"commit": {"statusCheckRollup": None}}]},
                },
            },
        }
        with patch("get_pr_checks.assert_gh_authenticated"), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch("get_pr_checks.gh_graphql", return_value=empty_gql):
            rc = main(["--pull-request", "42", "--output-format", "json"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)["Data"]
        assert output["HasChecks"] is False
        assert output["ChecksIncomplete"] is False


# ---------------------------------------------------------------------------
# Tests: normalize_check - additional coverage
# ---------------------------------------------------------------------------


class TestNormalizeCheckAdditional:
    def test_status_context_pending(self):
        ctx = {
            "__typename": "StatusContext",
            "context": "ci/pending",
            "state": "PENDING",
            "targetUrl": "",
            "isRequired": False,
        }
        result = normalize_check(ctx)
        assert result["IsPending"] is True
        assert result["IsPassing"] is False

    def test_status_context_expected(self):
        ctx = {
            "__typename": "StatusContext",
            "context": "ci/expected",
            "state": "EXPECTED",
            "targetUrl": "",
            "isRequired": False,
        }
        result = normalize_check(ctx)
        assert result["IsPending"] is True

    def test_status_context_failure(self):
        ctx = {
            "__typename": "StatusContext",
            "context": "ci/failing",
            "state": "FAILURE",
            "targetUrl": "",
            "isRequired": True,
        }
        result = normalize_check(ctx)
        assert result["IsFailing"] is True

    def test_status_context_error(self):
        ctx = {
            "__typename": "StatusContext",
            "context": "ci/error",
            "state": "ERROR",
            "targetUrl": "",
            "isRequired": True,
        }
        result = normalize_check(ctx)
        assert result["IsFailing"] is True

    def test_check_run_cancelled(self):
        ctx = {
            "__typename": "CheckRun",
            "name": "cancelled",
            "status": "COMPLETED",
            "conclusion": "CANCELLED",
            "detailsUrl": "",
            "isRequired": False,
        }
        result = normalize_check(ctx)
        assert result["IsFailing"] is True

    def test_check_run_neutral(self):
        ctx = {
            "__typename": "CheckRun",
            "name": "neutral",
            "status": "COMPLETED",
            "conclusion": "NEUTRAL",
            "detailsUrl": "",
            "isRequired": False,
        }
        result = normalize_check(ctx)
        assert result["IsPassing"] is True

    def test_check_run_skipped(self):
        ctx = {
            "__typename": "CheckRun",
            "name": "skipped",
            "status": "COMPLETED",
            "conclusion": "SKIPPED",
            "detailsUrl": "",
            "isRequired": False,
        }
        result = normalize_check(ctx)
        assert result["IsPassing"] is True

    def test_check_run_missing_fields(self):
        """Handles missing optional fields gracefully."""
        ctx = {"__typename": "CheckRun"}
        result = normalize_check(ctx)
        assert result["Name"] == ""
        assert result["State"] == ""
        assert result["Conclusion"] == ""

    def test_no_typename_returns_none(self):
        result = normalize_check({})
        assert result is None


# ---------------------------------------------------------------------------
# Tests: fetch_checks - unit tests
# ---------------------------------------------------------------------------


class TestFetchChecks:
    def test_not_found_error(self):
        with patch(
            "get_pr_checks.gh_graphql",
            side_effect=RuntimeError("Could not resolve to a PullRequest"),
        ):
            result = fetch_checks("o", "r", 999)
        assert result["Error"] == "NotFound"

    def test_generic_api_error(self):
        with patch(
            "get_pr_checks.gh_graphql",
            side_effect=RuntimeError("rate limit exceeded"),
        ):
            result = fetch_checks("o", "r", 1)
        assert result["Error"] == "ApiError"
        assert "rate limit" in result["Message"]

    def test_pr_none_in_response(self):
        with patch(
            "get_pr_checks.gh_graphql",
            return_value={"repository": {"pullRequest": None}},
        ):
            result = fetch_checks("o", "r", 1)
        assert result["Error"] == "NotFound"

    def test_empty_commits(self):
        with patch(
            "get_pr_checks.gh_graphql",
            return_value={
                "repository": {
                    "pullRequest": {
                        "number": 1,
                        "commits": {"nodes": []},
                    },
                },
            },
        ):
            result = fetch_checks("o", "r", 1)
        assert result["HasChecks"] is False
        assert result["OverallState"] == "UNKNOWN"

    def test_no_rollup(self):
        with patch(
            "get_pr_checks.gh_graphql",
            return_value={
                "repository": {
                    "pullRequest": {
                        "number": 1,
                        "commits": {
                            "nodes": [
                                {"commit": {"statusCheckRollup": None}},
                            ],
                        },
                    },
                },
            },
        ):
            result = fetch_checks("o", "r", 1)
        assert result["HasChecks"] is False


# ---------------------------------------------------------------------------
# Tests: build_output - additional coverage
# ---------------------------------------------------------------------------


class TestBuildOutputAdditional:
    def test_no_checks_not_all_passing(self):
        """No checks means AllPassing is False."""
        check_data = {
            "Number": 42,
            "HasChecks": True,
            "OverallState": "SUCCESS",
            "Checks": [],
        }
        output = build_output(check_data, "o", "r")
        assert output["AllPassing"] is False

    def test_pending_count(self):
        check_data = {
            "Number": 42,
            "HasChecks": True,
            "OverallState": "PENDING",
            "Checks": [
                {
                    "Name": "build", "IsPassing": False,
                    "IsFailing": False, "IsPending": True,
                    "IsRequired": True, "State": "IN_PROGRESS",
                    "Conclusion": "", "DetailsUrl": "",
                },
            ],
        }
        output = build_output(check_data, "o", "r")
        assert output["PendingCount"] == 1
        assert output["AllPassing"] is False

    def test_failed_pending_duplicate_counts_as_failed_and_pending(self):
        checks = dedupe_checks([
            _check("build", failing=True, conclusion="FAILURE"),
            _check("build", pending=True, state="IN_PROGRESS"),
        ])
        check_data = {
            "Number": 42,
            "HasChecks": True,
            "OverallState": "FAILURE",
            "Checks": checks,
        }
        output = build_output(check_data, "o", "r")
        assert output["FailedCount"] == 1
        assert output["PendingCount"] == 1
        assert output["AllPassing"] is False

    def test_passing_pending_duplicate_counts_as_pending_not_all_passing(self):
        checks = dedupe_checks([
            _check("build", passing=True, conclusion="SUCCESS"),
            _check("build", pending=True, state="IN_PROGRESS"),
        ])
        check_data = {
            "Number": 42,
            "HasChecks": True,
            "OverallState": "PENDING",
            "Checks": checks,
        }
        output = build_output(check_data, "o", "r")
        assert output["FailedCount"] == 0
        assert output["PendingCount"] == 1
        assert output["AllPassing"] is False

    def test_has_checks_false(self):
        check_data = {
            "Number": 42,
            "HasChecks": False,
            "OverallState": "UNKNOWN",
            "Checks": [],
        }
        output = build_output(check_data, "o", "r")
        assert output["AllPassing"] is False


# ---------------------------------------------------------------------------
# Tests: dedupe_checks (superseded check runs, Issue #2208)
# ---------------------------------------------------------------------------


class TestDedupeChecks:
    def test_empty_list_returns_empty(self):
        assert dedupe_checks([]) == []

    def test_single_check_passes_through(self):
        checks = [_check("build", passing=True)]
        assert dedupe_checks(checks) == checks

    def test_distinct_names_preserved_in_order(self):
        checks = [
            _check("build", passing=True),
            _check("test", failing=True),
            _check("lint", pending=True),
        ]
        result = dedupe_checks(checks)
        assert [c["Name"] for c in result] == ["build", "test", "lint"]

    def test_passing_supersedes_earlier_failure(self):
        """A re-run SUCCESS wins over a stale FAILURE for the same name."""
        checks = [
            _check("Validate PR", failing=True, conclusion="FAILURE"),
            _check("Validate PR", passing=True, conclusion="SUCCESS"),
        ]
        result = dedupe_checks(checks)
        assert len(result) == 1
        assert result[0]["IsPassing"] is True
        assert result[0]["IsFailing"] is False

    def test_passing_supersedes_later_failure(self):
        """Order does not matter: a passing run wins even when seen first."""
        checks = [
            _check("Validate PR", passing=True, conclusion="SUCCESS"),
            _check("Validate PR", failing=True, conclusion="FAILURE"),
        ]
        result = dedupe_checks(checks)
        assert len(result) == 1
        assert result[0]["IsPassing"] is True

    def test_required_status_survives_when_any_duplicate_is_required(self):
        """A required duplicate keeps the deduped row required."""
        checks = [
            _check("security", passing=True, conclusion="SUCCESS", required=False),
            _check("security", failing=True, conclusion="FAILURE", required=True),
        ]
        result = dedupe_checks(checks)
        assert len(result) == 1
        assert result[0]["IsPassing"] is True
        assert result[0]["IsRequired"] is True

    def test_null_name_collapses_to_empty_name(self):
        """Explicit null names dedupe through the empty-name bucket."""
        checks = [
            {**_check("ignored", failing=True, conclusion="FAILURE"), "Name": None},
            {**_check("", passing=True, conclusion="SUCCESS"), "Name": ""},
        ]
        result = dedupe_checks(checks)
        assert len(result) == 1
        assert result[0]["Name"] == ""
        assert result[0]["IsPassing"] is True

    def test_real_failure_with_no_passing_run_survives(self):
        """No passing run means the failing entry is kept (true failure)."""
        checks = [
            _check("test", failing=True, conclusion="FAILURE"),
            _check("test", failing=True, conclusion="TIMED_OUT"),
        ]
        result = dedupe_checks(checks)
        assert len(result) == 1
        assert result[0]["IsFailing"] is True

    def test_failure_supersedes_unknown_conclusion(self):
        """Unknown conclusions do not hide real failures."""
        checks = [
            _check("test", conclusion="UNKNOWN"),
            _check("test", failing=True, conclusion="FAILURE"),
        ]
        result = dedupe_checks(checks)
        assert len(result) == 1
        assert result[0]["Conclusion"] == "FAILURE"
        assert result[0]["IsFailing"] is True

    def test_failure_supersedes_pending_but_keeps_pending_signal(self):
        """A pending re-run keeps wait polling active after a failure."""
        checks = [
            _check("build", failing=True, conclusion="FAILURE"),
            _check("build", pending=True, state="IN_PROGRESS"),
        ]
        result = dedupe_checks(checks)
        assert len(result) == 1
        assert result[0]["IsFailing"] is True
        assert result[0]["IsPending"] is True

    def test_passing_supersedes_pending_but_keeps_pending_signal(self):
        """A same-name pending run keeps wait polling active."""
        checks = [
            _check("build", pending=True, state="IN_PROGRESS"),
            _check("build", passing=True, conclusion="SUCCESS"),
        ]
        result = dedupe_checks(checks)
        assert len(result) == 1
        assert result[0]["IsPassing"] is True
        assert result[0]["IsPending"] is True

    def test_status_context_dedupes_by_name(self):
        """StatusContext entries dedupe by Name like CheckRun entries."""
        checks = [
            {
                "Name": "ci/travis", "Type": "StatusContext",
                "State": "FAILURE", "Conclusion": "FAILURE", "DetailsUrl": "",
                "IsRequired": True, "IsPending": False,
                "IsPassing": False, "IsFailing": True,
            },
            {
                "Name": "ci/travis", "Type": "StatusContext",
                "State": "SUCCESS", "Conclusion": "SUCCESS", "DetailsUrl": "",
                "IsRequired": True, "IsPending": False,
                "IsPassing": True, "IsFailing": False,
            },
        ]
        result = dedupe_checks(checks)
        assert len(result) == 1
        assert result[0]["IsPassing"] is True

    def test_check_run_preferred_over_same_name_status_context(self):
        """A StatusContext duplicate cannot mask a failing CheckRun."""
        checks = [
            {
                "Name": "build", "Type": "StatusContext",
                "State": "SUCCESS", "Conclusion": "SUCCESS", "DetailsUrl": "",
                "IsRequired": True, "IsPending": False,
                "IsPassing": True, "IsFailing": False,
            },
            _check("build", failing=True, conclusion="FAILURE"),
        ]
        result = dedupe_checks(checks)
        assert len(result) == 1
        assert result[0]["Type"] == "CheckRun"
        assert result[0]["IsFailing"] is True


# ---------------------------------------------------------------------------
# Tests: fetch_checks + main with superseded runs (Issue #2208 scenario)
# ---------------------------------------------------------------------------


class TestSupersededCheckRuns:
    def test_fetch_checks_collapses_superseded_failure(self):
        """fetch_checks dedupes a stale FAILURE against a fresh SUCCESS."""
        nodes = [
            _check_run_node("Validate PR", "COMPLETED", "FAILURE"),
            _check_run_node("Validate PR", "COMPLETED", "SUCCESS"),
        ]
        with patch(
            "get_pr_checks.gh_graphql",
            return_value=_rollup_response(nodes),
        ):
            result = fetch_checks("o", "r", 2201)
        assert len(result["Checks"]) == 1
        assert result["Checks"][0]["IsPassing"] is True

    def test_main_superseded_failure_returns_0(self, capsys):
        """End-to-end: PR #2201 shape (stale FAILURE + fresh SUCCESS) is ready.

        Reproduces Issue #2208: an older Validate PR run failed while a newer
        run succeeded on the same commit. Before the fix, FailedCount was 1
        and the exit code was 1; after dedupe it is 0.
        """
        nodes = [
            _check_run_node("Validate PR", "COMPLETED", "FAILURE"),
            _check_run_node("Validate PR", "COMPLETED", "SUCCESS"),
        ]
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=_rollup_response(nodes),
        ):
            rc = main(["--pull-request", "2201"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["FailedCount"] == 0
        assert output["Data"]["PassedCount"] == 1
        assert output["Data"]["AllPassing"] is True

    def test_main_genuine_failure_still_returns_1(self, capsys):
        """A name with only failing runs still blocks (no false PASS)."""
        nodes = [
            _check_run_node("test", "COMPLETED", "FAILURE"),
            _check_run_node("test", "COMPLETED", "FAILURE"),
        ]
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=_rollup_response(nodes),
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 1
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["FailedCount"] == 1

    def test_main_cancelled_then_success_required_only_returns_0(self, capsys):
        """Regression for issue #2308: stale CANCELLED + fresh SUCCESS on a
        required check should exit 0 under --required-only.

        Reproduces PR #2289: ``Validate PR`` and ``Validate PR title`` each had
        a stale CANCELLED run alongside a fresh SUCCESS, both required. Before
        the fix this exited 1 and reported OverallState=FAILURE; after dedupe
        the SUCCESS wins and the script reports AllPassing=true.
        """
        nodes = [
            _check_run_node("Validate PR", "COMPLETED", "CANCELLED"),
            _check_run_node("Validate PR", "COMPLETED", "SUCCESS"),
            _check_run_node("Validate PR title", "COMPLETED", "CANCELLED"),
            _check_run_node("Validate PR title", "COMPLETED", "SUCCESS"),
        ]
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=_rollup_response(nodes),
        ):
            rc = main(["--pull-request", "2289", "--required-only"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        data = output["Data"]
        assert data["FailedCount"] == 0
        assert data["PassedCount"] == 2
        assert data["AllPassing"] is True
        # Each required check name appears exactly once after dedupe.
        names = [c["Name"] for c in data["Checks"]]
        assert names.count("Validate PR") == 1
        assert names.count("Validate PR title") == 1

    def test_dual_row_required_or_semantics(self, capsys):
        """Issue #2325: When a check name has both CheckRun (not required) and
        StatusContext (required), --required-only should include it because any
        row carries isRequired=true.

        Reproduces scenario: Analyst check publishes both a CheckRun and a
        StatusContext; the CheckRun is isRequired=false but the StatusContext is
        isRequired=true. The name should be treated as required.
        """
        nodes = [
           {
               "__typename": "CheckRun",
               "name": "Analyst",
               "status": "IN_PROGRESS",
               "conclusion": "",
               "detailsUrl": "",
               "isRequired": False,
           },
           {
               "__typename": "StatusContext",
               "context": "Analyst",
               "state": "PENDING",
               "targetUrl": "",
               "isRequired": True,
           },
        ]
        with patch(
           "get_pr_checks.assert_gh_authenticated",
        ), patch(
           "get_pr_checks.resolve_repo_params",
           return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
           "get_pr_checks.gh_graphql",
           return_value=_rollup_response(nodes),
        ):
           rc = main(["--pull-request", "2325", "--required-only"])
        # Must exit 7 (timeout pending) or return pending count > 0, not exit 0.
        # With --required-only, the Analyst check (required via StatusContext)
        # must appear in the output.
        output = json.loads(capsys.readouterr().out)
        data = output["Data"]
        assert data["PendingCount"] > 0, \
           "Expected pending count > 0 for pending required Analyst check"
        names = [c["Name"] for c in data["Checks"]]
        assert "Analyst" in names, \
           "Expected Analyst check in --required-only output (required via StatusContext)"
        checks = {c["Name"]: c for c in data["Checks"]}
        assert checks["Analyst"]["IsRequired"] is True, \
           "Expected Analyst check marked as required (OR of both rows)"

    def test_failed_required_check_required_only_includes_failed_list(self, capsys):
        """Issue #2325: --required-only output should expose FailedRequiredChecks
        list so downstream agents can distinguish pending vs. failed required checks.

        When a required check fails, it must appear in both Checks[] and
        FailedRequiredChecks[] (new field).
        """
        nodes = [
           _check_run_node("CI/lint", "COMPLETED", "FAILURE", required=True),
           _check_run_node("CI/test", "IN_PROGRESS", "", required=True),
        ]
        with patch(
           "get_pr_checks.assert_gh_authenticated",
        ), patch(
           "get_pr_checks.resolve_repo_params",
           return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
           "get_pr_checks.gh_graphql",
           return_value=_rollup_response(nodes),
        ):
           rc = main(["--pull-request", "2325", "--required-only"])
        output = json.loads(capsys.readouterr().out)
        data = output["Data"]
        # Should have both failed and pending required checks visible.
        assert data["FailedCount"] == 1
        assert data["PendingCount"] == 1
        # New fields for structured output to downstream agents.
        assert "FailedRequiredChecks" in data, \
           "Expected FailedRequiredChecks list in --required-only output"
        assert "PendingRequiredChecks" in data, \
           "Expected PendingRequiredChecks list in --required-only output"
        assert "CI/lint" in data["FailedRequiredChecks"], \
           "Expected failed required check in FailedRequiredChecks list"
        assert "CI/test" in data["PendingRequiredChecks"], \
           "Expected pending required check in PendingRequiredChecks list"
