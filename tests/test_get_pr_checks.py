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
