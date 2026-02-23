"""Tests for get_pr_checks.py skill script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

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

    def test_output_format_default_is_text(self):
        args = build_parser().parse_args(["--pull-request", "1"])
        assert args.output_format == "text"

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
            return_value={"Owner": "o", "Repo": "r"},
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
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["AllPassing"] is True

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
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])
        assert rc == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        output = json.loads(captured.out)
        assert output["AllPassing"] is True

    def test_output_format_text_includes_stderr(self, capsys):
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
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42", "--output-format", "text"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "All 1 check(s) passing" in captured.err

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
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42", "--output-format", "json"])
        assert rc == 1
        captured = capsys.readouterr()
        assert captured.err == ""
        output = json.loads(captured.out)
        assert output["FailedCount"] == 1

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
            return_value={"Owner": "o", "Repo": "r"},
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
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "get_pr_checks.gh_graphql",
            side_effect=RuntimeError("internal server error"),
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 3
        output = json.loads(capsys.readouterr().out)
        assert output["Success"] is False
        assert "internal server error" in output["Error"]

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
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["HasChecks"] is False
        assert output["OverallState"] == "UNKNOWN"

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
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["HasChecks"] is False

    def test_pr_not_in_response_returns_2(self, capsys):
        """PR not found in GraphQL response returns exit code 2."""
        gql_data = {"repository": {"pullRequest": None}}
        with patch(
            "get_pr_checks.assert_gh_authenticated",
        ), patch(
            "get_pr_checks.resolve_repo_params",
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 2
        output = json.loads(capsys.readouterr().out)
        assert output["Success"] is False

    def test_pending_checks_returns_0(self, capsys):
        """Pending checks (no --wait) return exit code 0 with stderr message."""
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
            return_value={"Owner": "o", "Repo": "r"},
        ), patch(
            "get_pr_checks.gh_graphql",
            return_value=gql_data,
        ):
            rc = main(["--pull-request", "42"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "pending" in captured.err

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
            return_value={"Owner": "o", "Repo": "r"},
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
            ])
        assert rc == 7
        captured = capsys.readouterr()
        assert "Timeout" in captured.err

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
            return_value={"Owner": "o", "Repo": "r"},
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

    def test_has_checks_false(self):
        check_data = {
            "Number": 42,
            "HasChecks": False,
            "OverallState": "UNKNOWN",
            "Checks": [],
        }
        output = build_output(check_data, "o", "r")
        assert output["AllPassing"] is False
