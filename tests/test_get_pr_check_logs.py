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
        assert output["FailingChecks"] == 0

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
        assert output["CheckLogs"][0]["LogSource"] == "external"
