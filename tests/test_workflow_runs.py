"""Tests for GitHub workflow-run analysis and concurrency grouping.

Split from test_ai_review.py (issue #1963). Covers get_pr_changed_files,
get_workflow_runs_by_pr, runs_overlap, and get_concurrency_group_from_run,
plus the shared _completed subprocess helper. Moved verbatim originally;
PR #5787 review changed get_pr_changed_files to raise instead of
returning [] on a failed call, and get_workflow_runs_by_pr to paginate.
"""

from __future__ import annotations

import json
import os
import subprocess
from unittest.mock import patch

import pytest

from scripts.ai_review_common import (
    get_concurrency_group_from_run,
    get_pr_changed_files,
    get_workflow_runs_by_pr,
    runs_overlap,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Workflow: PR changed files
# ---------------------------------------------------------------------------


class TestGetPRChangedFiles:
    def test_returns_filtered_files(self):
        stdout = "src/main.py\nREADME.md\nsrc/utils.py\n"
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}):
            with patch("subprocess.run", return_value=_completed(stdout=stdout)):
                result = get_pr_changed_files(123, pattern=r"(?i)\.py(?!\.\w)$")
        assert result == ["src/main.py", "src/utils.py"]

    def test_returns_all_when_no_pattern(self):
        stdout = "a.py\nb.md\n"
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}):
            with patch("subprocess.run", return_value=_completed(stdout=stdout)):
                result = get_pr_changed_files(42)
        assert len(result) == 2

    def test_raises_on_api_failure(self):
        """A failed API call must not be mistaken for zero changed files
        (CodeRabbit, PR #5787 review): a validation gate reading an
        empty list back cannot tell "call failed" from "PR changed
        nothing", and silently skips real changes in the former case."""
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}):
            with patch("subprocess.run", return_value=_completed(rc=1, stderr="err")):
                with pytest.raises(RuntimeError, match="Failed to get changed files"):
                    get_pr_changed_files(1)

    def test_raises_when_repository_undeterminable(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("subprocess.run", return_value=_completed(rc=1, stderr="no repo")):
                with pytest.raises(RuntimeError, match="Could not determine repository"):
                    get_pr_changed_files(1)

    def test_raises_on_timeout(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}):
            with patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30),
            ):
                with pytest.raises(RuntimeError, match="Failed to get changed files"):
                    get_pr_changed_files(1)

    def test_returns_empty_list_for_a_pr_with_genuinely_no_changed_files(self):
        """A successful call with empty output is a real empty result,
        not a failure, and must still return []."""
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}):
            with patch("subprocess.run", return_value=_completed(stdout="")):
                result = get_pr_changed_files(1)
        assert result == []


# ---------------------------------------------------------------------------
# Workflow: workflow run analysis
# ---------------------------------------------------------------------------


def _ndjson(runs: list[dict]) -> str:
    """Newline-delimited JSON: `gh api --paginate --jq ".workflow_runs[]"`'s
    real output shape (one JSON value per line, one per run, across every
    page), not a single JSON array document."""
    return "\n".join(json.dumps(run) for run in runs) + "\n"


class TestGetWorkflowRunsByPR:
    def test_returns_filtered_runs(self):
        runs = [
            {"name": "quality-gate", "pull_requests": [{"number": 42}]},
            {"name": "other", "pull_requests": [{"number": 99}]},
        ]
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=_ndjson(runs)),
        ):
            result = get_workflow_runs_by_pr(42, repository="owner/repo")
        assert len(result) == 1
        assert result[0]["name"] == "quality-gate"

    def test_filters_by_workflow_name(self):
        runs = [
            {"name": "ai-quality-gate", "pull_requests": [{"number": 42}]},
            {"name": "label-pr", "pull_requests": [{"number": 42}]},
        ]
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=_ndjson(runs)),
        ):
            result = get_workflow_runs_by_pr(42, workflow_name="quality", repository="o/r")
        assert len(result) == 1

    def test_combines_runs_across_multiple_pages(self):
        """A PR whose run sits beyond the first 100 repo-wide runs must
        still be found: --paginate requests every page, and each page's
        workflow_runs[] elements land as more lines in the same stdout
        stream (CodeRabbit, PR #5787 review)."""
        page1 = [{"name": f"run-{i}", "pull_requests": [{"number": 99}]} for i in range(100)]
        page2 = [{"name": "the-target-run", "pull_requests": [{"number": 42}]}]
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=_ndjson(page1 + page2)),
        ):
            result = get_workflow_runs_by_pr(42, repository="owner/repo")
        assert len(result) == 1
        assert result[0]["name"] == "the-target-run"

    def test_uses_paginate_flag(self):
        captured: dict = {}

        def _fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return _completed(stdout=_ndjson([]))

        with patch("subprocess.run", side_effect=_fake_run):
            get_workflow_runs_by_pr(42, repository="owner/repo")
        assert "--paginate" in captured["cmd"]

    def test_raises_on_api_failure(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=1, stderr="API error"),
        ):
            with pytest.raises(RuntimeError, match="Failed to get workflow runs"):
                get_workflow_runs_by_pr(1, repository="o/r")

    def test_invalid_json_response_raises(self):
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="not json"),
        ):
            with pytest.raises(RuntimeError, match="Invalid JSON"):
                get_workflow_runs_by_pr(1, repository="o/r")

    def test_raises_when_gh_executable_missing(self):
        """FileNotFoundError from a missing `gh` binary must not escape as
        an unhandled exception; get_pr_changed_files already catches this
        for its own gh call, get_workflow_runs_by_pr did not (CodeRabbit,
        PR #5787 review)."""
        with patch("subprocess.run", side_effect=FileNotFoundError("gh not found")):
            with pytest.raises(RuntimeError, match="Failed to get workflow runs"):
                get_workflow_runs_by_pr(1, repository="o/r")

    def test_raises_on_gh_call_timeout(self):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30),
        ):
            with pytest.raises(RuntimeError, match="Failed to get workflow runs"):
                get_workflow_runs_by_pr(1, repository="o/r")


class TestRunsOverlap:
    def test_overlapping_runs(self):
        run1 = {"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T01:00:00Z"}
        run2 = {"created_at": "2026-01-01T00:30:00Z", "updated_at": "2026-01-01T01:30:00Z"}
        assert runs_overlap(run1, run2) is True

    def test_non_overlapping_runs(self):
        run1 = {"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T01:00:00Z"}
        run2 = {"created_at": "2026-01-01T02:00:00Z", "updated_at": "2026-01-01T03:00:00Z"}
        assert runs_overlap(run1, run2) is False

    def test_run2_starts_exactly_at_run1_end(self):
        # Boundary touch (run1.end == run2.start) is NOT overlap.
        # Half-open interval semantics: [start, end) -- the endpoint is exclusive.
        run1 = {"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T01:00:00Z"}
        run2 = {"created_at": "2026-01-01T01:00:00Z", "updated_at": "2026-01-01T02:00:00Z"}
        assert runs_overlap(run1, run2) is False

    def test_run1_starts_inside_run2(self):
        # Symmetric case: run1 starts inside run2. Previously a false-negative
        # because the old implementation only checked `run2_start` between
        # `run1_start` and `run1_end`.
        run1 = {"created_at": "2026-01-01T00:30:00Z", "updated_at": "2026-01-01T01:30:00Z"}
        run2 = {"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T01:00:00Z"}
        assert runs_overlap(run1, run2) is True

    def test_run1_fully_contains_run2(self):
        run1 = {"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T02:00:00Z"}
        run2 = {"created_at": "2026-01-01T00:30:00Z", "updated_at": "2026-01-01T01:30:00Z"}
        assert runs_overlap(run1, run2) is True

    def test_run2_fully_contains_run1(self):
        run1 = {"created_at": "2026-01-01T00:30:00Z", "updated_at": "2026-01-01T01:30:00Z"}
        run2 = {"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T02:00:00Z"}
        assert runs_overlap(run1, run2) is True

    def test_run1_starts_exactly_at_run2_end(self):
        # Symmetric boundary touch.
        run1 = {"created_at": "2026-01-01T01:00:00Z", "updated_at": "2026-01-01T02:00:00Z"}
        run2 = {"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T01:00:00Z"}
        assert runs_overlap(run1, run2) is False


class TestGetConcurrencyGroupFromRun:
    def test_quality_gate_pr(self):
        run = {
            "name": "ai-quality-gate",
            "event": "pull_request",
            "pull_requests": [{"number": 42}],
            "head_branch": "feat/test",
        }
        assert get_concurrency_group_from_run(run) == "ai-quality-42"

    def test_spec_validation_pr(self):
        run = {
            "name": "spec-validation",
            "event": "pull_request",
            "pull_requests": [{"number": 10}],
            "head_branch": "feat/spec",
        }
        assert get_concurrency_group_from_run(run) == "spec-validation-10"

    def test_label_pr(self):
        run = {
            "name": "label-pr",
            "event": "pull_request",
            "pull_requests": [{"number": 5}],
            "head_branch": "feat/label",
        }
        assert get_concurrency_group_from_run(run) == "label-pr-5"

    def test_default_prefix_for_unknown_workflow(self):
        run = {
            "name": "custom-workflow",
            "event": "pull_request",
            "pull_requests": [{"number": 7}],
            "head_branch": "feat/x",
        }
        assert get_concurrency_group_from_run(run) == "pr-validation-7"

    def test_fallback_without_pr(self):
        run = {
            "name": "nightly-build",
            "event": "schedule",
            "pull_requests": [],
            "head_branch": "main",
        }
        assert get_concurrency_group_from_run(run) == "nightly-build-main"
