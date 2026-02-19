"""Tests for PR Maintenance module, matching Pester coverage from PRMaintenanceModule.Tests.ps1."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.pr_maintenance import (
    EnvironmentResult,
    MaintenanceResults,
    RateLimitResult,
    check_workflow_environment,
    check_workflow_rate_limit,
    create_blocked_prs_alert,
    create_maintenance_summary,
    create_workflow_failure_alert,
    get_maintenance_results,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

RATE_LIMIT_ALL_OK = json.dumps(
    {
        "resources": {
            "core": {"remaining": 5000, "limit": 5000, "reset": 1234567890},
            "search": {"remaining": 30, "limit": 30, "reset": 1234567890},
            "code_search": {"remaining": 10, "limit": 10, "reset": 1234567890},
            "graphql": {"remaining": 5000, "limit": 5000, "reset": 1234567890},
        }
    }
)

RATE_LIMIT_CORE_LOW = json.dumps(
    {
        "resources": {
            "core": {"remaining": 50, "limit": 5000, "reset": 1234567890},
            "search": {"remaining": 30, "limit": 30, "reset": 1234567890},
            "code_search": {"remaining": 10, "limit": 10, "reset": 1234567890},
            "graphql": {"remaining": 5000, "limit": 5000, "reset": 1234567890},
        }
    }
)

RATE_LIMIT_SEARCH_LOW = json.dumps(
    {
        "resources": {
            "core": {"remaining": 5000, "limit": 5000, "reset": 1234567890},
            "search": {"remaining": 5, "limit": 30, "reset": 1234567890},
            "code_search": {"remaining": 10, "limit": 10, "reset": 1234567890},
            "graphql": {"remaining": 5000, "limit": 5000, "reset": 1234567890},
        }
    }
)

RATE_LIMIT_CUSTOM = json.dumps(
    {
        "resources": {
            "core": {"remaining": 150, "limit": 5000, "reset": 1234567890},
            "search": {"remaining": 30, "limit": 30, "reset": 1234567890},
            "code_search": {"remaining": 10, "limit": 10, "reset": 1234567890},
            "graphql": {"remaining": 5000, "limit": 5000, "reset": 1234567890},
        }
    }
)


def _mock_subprocess_run(stdout: str):
    """Return a mock for subprocess.run that returns given stdout."""

    def _side_effect(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout=stdout, stderr=""
        )

    return _side_effect


def _mock_subprocess_run_failure():
    """Return a mock for subprocess.run that raises CalledProcessError."""

    def _side_effect(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1, cmd=args[0], output="Error: API error"
        )

    return _side_effect


# ---------------------------------------------------------------------------
# check_workflow_rate_limit
# ---------------------------------------------------------------------------


class TestCheckWorkflowRateLimit:
    def test_success_when_all_above_threshold(self):
        with patch("subprocess.run", side_effect=_mock_subprocess_run(RATE_LIMIT_ALL_OK)):
            result = check_workflow_rate_limit()

        assert result.success is True
        assert result.core_remaining == 5000

    def test_failure_when_core_below_threshold(self):
        with patch("subprocess.run", side_effect=_mock_subprocess_run(RATE_LIMIT_CORE_LOW)):
            result = check_workflow_rate_limit()

        assert result.success is False
        assert result.resources["core"]["Passed"] is False

    def test_failure_when_search_below_threshold(self):
        with patch("subprocess.run", side_effect=_mock_subprocess_run(RATE_LIMIT_SEARCH_LOW)):
            result = check_workflow_rate_limit()

        assert result.success is False
        assert result.resources["search"]["Passed"] is False

    def test_custom_thresholds_pass(self):
        with patch("subprocess.run", side_effect=_mock_subprocess_run(RATE_LIMIT_CUSTOM)):
            result = check_workflow_rate_limit(resource_thresholds={"core": 100})

        assert result.success is True

    def test_custom_thresholds_fail(self):
        with patch("subprocess.run", side_effect=_mock_subprocess_run(RATE_LIMIT_CUSTOM)):
            result = check_workflow_rate_limit(resource_thresholds={"core": 200})

        assert result.success is False

    def test_markdown_summary_generated(self):
        with patch("subprocess.run", side_effect=_mock_subprocess_run(RATE_LIMIT_ALL_OK)):
            result = check_workflow_rate_limit()

        assert "API Rate Limit Status" in result.summary_markdown
        assert "| Resource |" in result.summary_markdown
        assert "OK" in result.summary_markdown

    def test_raises_on_gh_failure(self):
        def _fail(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args[0], returncode=1, stdout="", stderr="API error"
            )

        with patch("subprocess.run", side_effect=_fail):
            with pytest.raises(RuntimeError, match="Failed to fetch rate limits"):
                check_workflow_rate_limit()

    def test_returns_rate_limit_result_type(self):
        with patch("subprocess.run", side_effect=_mock_subprocess_run(RATE_LIMIT_ALL_OK)):
            result = check_workflow_rate_limit()

        assert isinstance(result, RateLimitResult)


# ---------------------------------------------------------------------------
# get_maintenance_results
# ---------------------------------------------------------------------------


class TestGetMaintenanceResults:
    def test_parse_metrics(self, tmp_path: Path):
        log_file = tmp_path / "test.log"
        log_file.write_text(
            "[2025-01-01 00:00:00] Starting PR Maintenance\n"
            "PRs Processed: 5\n"
            "Comments Acknowledged: 12\n"
            "Conflicts Resolved: 2\n",
            encoding="utf-8",
        )

        result = get_maintenance_results(log_file)

        assert result.processed == 5
        assert result.acknowledged == 12
        assert result.resolved == 2
        assert result.has_blocked is False

    def test_extract_blocked_prs(self, tmp_path: Path):
        log_file = tmp_path / "test.log"
        log_file.write_text(
            "[2025-01-01 00:00:00] Starting PR Maintenance\n"
            "PRs Processed: 3\n"
            "Comments Acknowledged: 5\n"
            "Conflicts Resolved: 0\n"
            "Blocked PRs (require human action):\n"
            "  PR #123 - Merge conflicts cannot be auto-resolved\n"
            "  PR #456 - Changes requested by reviewer\n",
            encoding="utf-8",
        )

        result = get_maintenance_results(log_file)

        assert result.has_blocked is True
        assert len(result.blocked_prs) == 2
        assert "PR #123" in result.blocked_prs[0]
        assert "PR #456" in result.blocked_prs[1]

    def test_missing_file_returns_zeros(self):
        with pytest.warns(UserWarning, match="Log file not found"):
            result = get_maintenance_results("nonexistent.log")

        assert result.processed == 0
        assert result.acknowledged == 0
        assert result.resolved == 0
        assert result.has_blocked is False

    def test_no_metrics_in_log(self, tmp_path: Path):
        log_file = tmp_path / "test.log"
        log_file.write_text(
            "[2025-01-01 00:00:00] Starting PR Maintenance\n"
            "[2025-01-01 00:00:01] No PRs found to process\n",
            encoding="utf-8",
        )

        result = get_maintenance_results(log_file)

        assert result.processed == 0
        assert result.acknowledged == 0
        assert result.resolved == 0

    def test_large_metric_values(self, tmp_path: Path):
        log_file = tmp_path / "test.log"
        log_file.write_text(
            "PRs Processed: 999\n"
            "Comments Acknowledged: 12345\n"
            "Conflicts Resolved: 100\n",
            encoding="utf-8",
        )

        result = get_maintenance_results(log_file)

        assert result.processed == 999
        assert result.acknowledged == 12345
        assert result.resolved == 100

    def test_returns_maintenance_results_type(self, tmp_path: Path):
        log_file = tmp_path / "test.log"
        log_file.write_text("PRs Processed: 1\n", encoding="utf-8")

        result = get_maintenance_results(log_file)

        assert isinstance(result, MaintenanceResults)

    def test_rejects_relative_path_traversal(self):
        with pytest.raises(ValueError, match="Relative path traversal"):
            get_maintenance_results("../../etc/passwd")

    def test_allows_absolute_path(self, tmp_path: Path):
        log_file = tmp_path / "test.log"
        log_file.write_text("PRs Processed: 1\n", encoding="utf-8")
        result = get_maintenance_results(str(log_file.resolve()))
        assert result.processed == 1


# ---------------------------------------------------------------------------
# create_maintenance_summary
# ---------------------------------------------------------------------------


class TestCreateMaintenanceSummary:
    def test_basic_summary(self):
        results = MaintenanceResults(
            processed=5,
            acknowledged=12,
            resolved=2,
            blocked_prs=[],
            has_blocked=False,
        )

        summary = create_maintenance_summary(results, core_remaining=4500)

        assert "PR Maintenance Summary" in summary
        assert re.search(r"PRs Processed.*5", summary)
        assert re.search(r"Comments Acknowledged.*12", summary)
        assert re.search(r"Conflicts Resolved.*2", summary)
        assert re.search(r"Core API.*4500", summary)

    def test_includes_blocked_prs(self):
        results = MaintenanceResults(
            processed=3,
            acknowledged=5,
            resolved=0,
            blocked_prs=["PR #123 - conflicts", "PR #456 - changes requested"],
            has_blocked=True,
        )

        summary = create_maintenance_summary(results, core_remaining=4000)

        assert "Blocked PRs (Require Human Action)" in summary
        assert "PR #123" in summary
        assert "PR #456" in summary

    def test_includes_run_url(self):
        results = MaintenanceResults(
            processed=1,
            acknowledged=1,
            resolved=0,
            blocked_prs=[],
            has_blocked=False,
        )
        run_url = "https://github.com/owner/repo/actions/runs/12345"

        summary = create_maintenance_summary(results, run_url=run_url)

        assert "View Logs" in summary
        assert run_url in summary

    def test_no_run_url_omits_link(self):
        results = MaintenanceResults(
            processed=1,
            acknowledged=0,
            resolved=0,
            blocked_prs=[],
            has_blocked=False,
        )

        summary = create_maintenance_summary(results)

        assert "View Logs" not in summary

    def test_contains_timestamp(self):
        results = MaintenanceResults(
            processed=0,
            acknowledged=0,
            resolved=0,
            blocked_prs=[],
            has_blocked=False,
        )

        summary = create_maintenance_summary(results)

        assert re.search(r"\d{4}-\d{2}-\d{2}", summary)


# ---------------------------------------------------------------------------
# create_blocked_prs_alert
# ---------------------------------------------------------------------------


class TestCreateBlockedPrsAlert:
    def test_alert_body_with_blocked_prs(self):
        blocked_prs = [
            "PR #123 - Merge conflicts",
            "PR #456 - Changes requested",
        ]

        body = create_blocked_prs_alert(blocked_prs)

        assert "Blocked PRs" in body
        assert "PR #123" in body
        assert "PR #456" in body
        assert "Action Required" in body

    def test_includes_run_url(self):
        run_url = "https://github.com/owner/repo/actions/runs/99999"

        body = create_blocked_prs_alert(["PR #789 - Issue"], run_url=run_url)

        assert "Workflow Run" in body
        assert run_url in body

    def test_includes_footer(self):
        body = create_blocked_prs_alert(["PR #1"])

        assert "Powered by" in body
        assert "PR Maintenance" in body


# ---------------------------------------------------------------------------
# create_workflow_failure_alert
# ---------------------------------------------------------------------------


class TestCreateWorkflowFailureAlert:
    def test_failure_alert_body(self):
        body = create_workflow_failure_alert(trigger_event="schedule")

        assert "Workflow Failure" in body
        assert "schedule" in body
        assert "Action Required" in body
        assert "Investigate workflow logs" in body

    def test_includes_run_url(self):
        run_url = "https://github.com/owner/repo/actions/runs/55555"

        body = create_workflow_failure_alert(
            run_url=run_url, trigger_event="workflow_dispatch"
        )

        assert run_url in body
        assert "workflow_dispatch" in body

    def test_includes_timestamp(self):
        body = create_workflow_failure_alert()

        assert re.search(r"\d{4}-\d{2}-\d{2}", body)

    def test_includes_footer(self):
        body = create_workflow_failure_alert()

        assert "Powered by" in body
        assert "PR Maintenance" in body


# ---------------------------------------------------------------------------
# check_workflow_environment
# ---------------------------------------------------------------------------


class TestCheckWorkflowEnvironment:
    def test_valid_when_all_tools_available(self):
        gh_output = "gh version 2.60.0 (2025-01-01)\n"
        git_output = "git version 2.43.0\n"

        def _side_effect(args, **kwargs):
            cmd = args[0]
            if cmd == "gh":
                return subprocess.CompletedProcess(args, 0, stdout=gh_output, stderr="")
            if cmd == "git":
                return subprocess.CompletedProcess(args, 0, stdout=git_output, stderr="")
            raise FileNotFoundError(cmd)

        with patch("subprocess.run", side_effect=_side_effect):
            result = check_workflow_environment()

        assert result.valid is True
        assert result.versions["Python"]
        assert result.versions["gh"] != "NOT FOUND"
        assert result.versions["git"] != "NOT FOUND"

    def test_invalid_when_gh_missing(self):
        git_output = "git version 2.43.0\n"

        def _side_effect(args, **kwargs):
            cmd = args[0]
            if cmd == "gh":
                raise FileNotFoundError("gh")
            if cmd == "git":
                return subprocess.CompletedProcess(args, 0, stdout=git_output, stderr="")
            raise FileNotFoundError(cmd)

        with patch("subprocess.run", side_effect=_side_effect):
            result = check_workflow_environment()

        assert result.valid is False
        assert result.versions["gh"] == "NOT FOUND"

    def test_invalid_when_git_missing(self):
        gh_output = "gh version 2.60.0 (2025-01-01)\n"

        def _side_effect(args, **kwargs):
            cmd = args[0]
            if cmd == "gh":
                return subprocess.CompletedProcess(args, 0, stdout=gh_output, stderr="")
            if cmd == "git":
                raise FileNotFoundError("git")
            raise FileNotFoundError(cmd)

        with patch("subprocess.run", side_effect=_side_effect):
            result = check_workflow_environment()

        assert result.valid is False
        assert result.versions["git"] == "NOT FOUND"

    def test_includes_python_version(self):
        gh_output = "gh version 2.60.0\n"
        git_output = "git version 2.43.0\n"

        def _side_effect(args, **kwargs):
            cmd = args[0]
            if cmd == "gh":
                return subprocess.CompletedProcess(args, 0, stdout=gh_output, stderr="")
            if cmd == "git":
                return subprocess.CompletedProcess(args, 0, stdout=git_output, stderr="")
            raise FileNotFoundError(cmd)

        with patch("subprocess.run", side_effect=_side_effect):
            result = check_workflow_environment()

        expected_version = sys.version.split()[0]
        assert result.versions["Python"] == expected_version

    def test_markdown_summary_structure(self):
        gh_output = "gh version 2.60.0\n"
        git_output = "git version 2.43.0\n"

        def _side_effect(args, **kwargs):
            cmd = args[0]
            if cmd == "gh":
                return subprocess.CompletedProcess(args, 0, stdout=gh_output, stderr="")
            if cmd == "git":
                return subprocess.CompletedProcess(args, 0, stdout=git_output, stderr="")
            raise FileNotFoundError(cmd)

        with patch("subprocess.run", side_effect=_side_effect):
            result = check_workflow_environment()

        assert "Environment Validation" in result.summary_markdown
        assert "| Tool |" in result.summary_markdown
        assert "Python" in result.summary_markdown

    def test_returns_environment_result_type(self):
        gh_output = "gh version 2.60.0\n"
        git_output = "git version 2.43.0\n"

        def _side_effect(args, **kwargs):
            cmd = args[0]
            if cmd == "gh":
                return subprocess.CompletedProcess(args, 0, stdout=gh_output, stderr="")
            if cmd == "git":
                return subprocess.CompletedProcess(args, 0, stdout=git_output, stderr="")
            raise FileNotFoundError(cmd)

        with patch("subprocess.run", side_effect=_side_effect):
            result = check_workflow_environment()

        assert isinstance(result, EnvironmentResult)


# ---------------------------------------------------------------------------
# Integration scenarios
# ---------------------------------------------------------------------------


class TestIntegrationScenarios:
    def test_complete_happy_path(self, tmp_path: Path):
        log_file = tmp_path / "integration-test.log"
        log_file.write_text(
            "PRs Processed: 10\n"
            "Comments Acknowledged: 25\n"
            "Conflicts Resolved: 3\n",
            encoding="utf-8",
        )

        results = get_maintenance_results(log_file)
        summary = create_maintenance_summary(results, core_remaining=4000)

        assert results.processed == 10
        assert re.search(r"PRs Processed.*10", summary)
        assert re.search(r"Comments Acknowledged.*25", summary)

    def test_blocked_prs_workflow(self, tmp_path: Path):
        log_file = tmp_path / "blocked-test.log"
        log_file.write_text(
            "PRs Processed: 5\n"
            "Comments Acknowledged: 8\n"
            "Conflicts Resolved: 0\n"
            "Blocked PRs (require human action):\n"
            "  PR #100 - Cannot auto-merge\n"
            "  PR #200 - Review required\n",
            encoding="utf-8",
        )

        results = get_maintenance_results(log_file)
        summary = create_maintenance_summary(results)
        alert_body = create_blocked_prs_alert(results.blocked_prs)

        assert results.has_blocked is True
        assert "Blocked PRs" in summary
        assert "PR #100" in alert_body
        assert "PR #200" in alert_body
