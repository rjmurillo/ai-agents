"""Tests for get_pr_check_logs.py skill script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
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


_mod = _import_script("get_pr_check_logs")
main = _mod.main
build_parser = _mod.build_parser
get_run_id_from_url = _mod.get_run_id_from_url
get_job_id_from_url = _mod.get_job_id_from_url
is_github_actions_url = _mod.is_github_actions_url
get_failure_snippets = _mod.get_failure_snippets
_is_failing = _mod._is_failing


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Tests: URL parsing
# ---------------------------------------------------------------------------


class TestUrlParsing:
    def test_get_run_id(self):
        url = "https://github.com/org/repo/actions/runs/12345678/job/9999"
        assert get_run_id_from_url(url) == "12345678"

    def test_get_run_id_no_match(self):
        assert get_run_id_from_url("https://example.com") is None

    def test_get_job_id(self):
        url = "https://github.com/org/repo/actions/runs/123/job/456"
        assert get_job_id_from_url(url) == "456"

    def test_get_job_id_no_match(self):
        assert get_job_id_from_url("https://example.com") is None

    def test_is_github_actions_url_true(self):
        assert is_github_actions_url("https://github.com/org/repo/actions/runs/123")

    def test_is_github_actions_url_false(self):
        assert not is_github_actions_url("https://circleci.com/build/123")

    def test_is_github_actions_url_empty(self):
        assert not is_github_actions_url("")


# ---------------------------------------------------------------------------
# Tests: get_failure_snippets
# ---------------------------------------------------------------------------


class TestGetFailureSnippets:
    def test_finds_error_lines(self):
        lines = [
            "Step 1: Setup",
            "Downloading...",
            "ERROR: Build failed",
            "See logs for details",
            "Step 2: Cleanup",
        ]
        snippets = get_failure_snippets(lines, context_lines=1, max_lines=100)
        assert len(snippets) >= 1
        assert "ERROR" in snippets[0]["MatchedLine"]

    def test_empty_log(self):
        assert get_failure_snippets([], context_lines=1, max_lines=100) == []

    def test_max_lines_limit(self):
        lines = [f"ERROR: failure {i}" for i in range(50)]
        snippets = get_failure_snippets(lines, context_lines=0, max_lines=5)
        total_extracted = sum(len(s["Context"].splitlines()) for s in snippets)
        assert total_extracted <= 5

    def test_context_lines(self):
        lines = [
            "before1",
            "before2",
            "ERROR: something failed",
            "after1",
            "after2",
        ]
        snippets = get_failure_snippets(lines, context_lines=2, max_lines=100)
        assert len(snippets) == 1
        assert "before1" in snippets[0]["Context"]
        assert "after2" in snippets[0]["Context"]


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_defaults(self):
        args = build_parser().parse_args([])
        assert args.pull_request == 0
        assert args.max_lines == 160
        assert args.context_lines == 30


class TestIsFailing:
    def test_rejects_non_dict_check(self):
        with pytest.raises(TypeError, match="check must be a dict"):
            _is_failing("not-a-check")


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "get_pr_check_logs.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
            assert exc.value.code == 4

    def test_no_pr_or_input_returns_1(self, capsys):
        with patch("get_pr_check_logs.assert_gh_authenticated"), patch(
            "get_pr_check_logs.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            rc = main([])
        assert rc == 1
        output = json.loads(capsys.readouterr().out)
        assert output["Success"] is False

    def test_pipeline_mode_no_failures(self, capsys):
        checks_json = json.dumps({
            "Success": True,
            "Number": 42,
            "Checks": [
                {"Name": "build", "Conclusion": "SUCCESS", "DetailsUrl": ""},
            ],
        })
        with patch("get_pr_check_logs.assert_gh_authenticated"), patch(
            "get_pr_check_logs.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            rc = main(["--checks-input", checks_json])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["FailingChecks"] == 0

    def test_pipeline_mode_enveloped_payload_finds_failures(self, capsys):
        """Regression for #2256: pipeline mode must unwrap the Data envelope."""
        checks_json = json.dumps({
            "Success": True,
            "Data": {
                "Number": 2240,
                "Checks": [
                    {
                        "Name": "Validate Spec Coverage",
                        "Conclusion": "FAILURE",
                        "IsRequired": True,
                        "DetailsUrl": "https://circleci.com/build/123",
                    },
                    {
                        "Name": "build",
                        "Conclusion": "SUCCESS",
                        "IsRequired": True,
                        "DetailsUrl": "",
                    },
                ],
                "FailedCount": 1,
                "HasChecks": True,
            },
            "Error": None,
            "Metadata": {},
        })
        with patch("get_pr_check_logs.assert_gh_authenticated"), patch(
            "get_pr_check_logs.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            rc = main(["--checks-input", checks_json])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["FailingChecks"] == 1
        assert output["Data"]["PullRequest"] == 2240

    def test_pipeline_mode_null_data_fails_loud(self, capsys):
        checks_json = json.dumps({"Success": True, "Data": None, "Error": None})
        with patch("get_pr_check_logs.assert_gh_authenticated"), patch(
            "get_pr_check_logs.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            rc = main(["--checks-input", checks_json])
        assert rc == 1
        output = json.loads(capsys.readouterr().out)
        assert output["Success"] is False
        assert "malformed Data payload" in output["Error"]["Message"]

    def test_pipeline_mode_null_checks_returns_no_failures(self, capsys):
        checks_json = json.dumps({
            "Success": True,
            "Data": {"Number": 2240, "Checks": None},
            "Error": None,
            "Metadata": {},
        })
        with patch("get_pr_check_logs.assert_gh_authenticated"), patch(
            "get_pr_check_logs.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            rc = main(["--checks-input", checks_json])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["FailingChecks"] == 0
        assert output["Data"]["PullRequest"] == 2240

    def test_pipeline_mode_malformed_checks_fails_loud(self, capsys):
        checks_json = json.dumps({
            "Success": True,
            "Data": {"Number": 2240, "Checks": "not-a-list"},
            "Error": None,
            "Metadata": {},
        })
        with patch("get_pr_check_logs.assert_gh_authenticated"), patch(
            "get_pr_check_logs.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            rc = main(["--checks-input", checks_json])
        assert rc == 1
        output = json.loads(capsys.readouterr().out)
        assert output["Success"] is False
        assert "malformed Checks payload" in output["Error"]["Message"]

    def test_pipeline_mode_malformed_check_item_fails_loud(self, capsys):
        checks_json = json.dumps({
            "Success": True,
            "Data": {"Number": 2240, "Checks": ["not-a-check"]},
            "Error": None,
            "Metadata": {},
        })
        with patch("get_pr_check_logs.assert_gh_authenticated"), patch(
            "get_pr_check_logs.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            rc = main(["--checks-input", checks_json])
        assert rc == 1
        output = json.loads(capsys.readouterr().out)
        assert output["Success"] is False
        assert "malformed Checks payload" in output["Error"]["Message"]

    def test_pipeline_mode_external_ci(self, capsys):
        checks_json = json.dumps({
            "Success": True,
            "Number": 42,
            "Checks": [
                {
                    "Name": "external",
                    "Conclusion": "FAILURE",
                    "DetailsUrl": "https://circleci.com/build/123",
                },
            ],
        })
        with patch("get_pr_check_logs.assert_gh_authenticated"), patch(
            "get_pr_check_logs.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            rc = main(["--checks-input", checks_json])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["CheckLogs"][0]["LogSource"] == "external"

    def test_status_context_error_is_failing_via_flag(self, capsys):
        # Regression for #2291: a StatusContext in ERROR state carries
        # IsFailing=True and Conclusion="ERROR". It must be treated as failing,
        # not reported as "no failing checks".
        checks_json = json.dumps({
            "Success": True,
            "Number": 42,
            "Checks": [
                {
                    "Name": "Validate PR",
                    "Type": "StatusContext",
                    "Conclusion": "ERROR",
                    "IsFailing": True,
                    "DetailsUrl": "https://example.com/status/1",
                },
            ],
        })
        with patch("get_pr_check_logs.assert_gh_authenticated"), patch(
            "get_pr_check_logs.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            rc = main(["--checks-input", checks_json])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["FailingChecks"] == 1

    def test_error_conclusion_is_failing_via_fallback(self, capsys):
        # Regression for #2291: when a check lacks the producer-computed
        # IsFailing flag, Conclusion="ERROR" must still count as failing.
        checks_json = json.dumps({
            "Success": True,
            "Number": 42,
            "Checks": [
                {
                    "Name": "Validate PR",
                    "Conclusion": "ERROR",
                    "DetailsUrl": "https://example.com/status/1",
                },
            ],
        })
        with patch("get_pr_check_logs.assert_gh_authenticated"), patch(
            "get_pr_check_logs.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            rc = main(["--checks-input", checks_json])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["FailingChecks"] == 1

    def test_passing_status_context_not_failing(self, capsys):
        # IsFailing=False must be honored even though dict.get default differs.
        checks_json = json.dumps({
            "Success": True,
            "Number": 42,
            "Checks": [
                {
                    "Name": "Validate PR",
                    "Type": "StatusContext",
                    "Conclusion": "SUCCESS",
                    "IsFailing": False,
                    "DetailsUrl": "",
                },
            ],
        })
        with patch("get_pr_check_logs.assert_gh_authenticated"), patch(
            "get_pr_check_logs.resolve_repo_params",
            return_value=RepoInfo(owner="o", repo="r"),
        ):
            rc = main(["--checks-input", checks_json])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["FailingChecks"] == 0
