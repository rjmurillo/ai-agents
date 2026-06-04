"""Tests for GitHub workflow-run analysis and concurrency grouping.

Split from test_ai_review.py (issue #1963). Covers get_pr_changed_files,
get_workflow_runs_by_pr, runs_overlap, and get_concurrency_group_from_run,
plus the shared _completed subprocess helper. Moved verbatim; behavior unchanged.
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
                result = get_pr_changed_files(123, pattern=r"\.py$")
        assert result == ["src/main.py", "src/utils.py"]

    def test_returns_all_when_no_pattern(self):
        stdout = "a.py\nb.md\n"
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}):
            with patch("subprocess.run", return_value=_completed(stdout=stdout)):
                result = get_pr_changed_files(42)
        assert len(result) == 2

    def test_returns_empty_on_failure(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}):
            with patch("subprocess.run", return_value=_completed(rc=1, stderr="err")):
                result = get_pr_changed_files(1)
        assert result == []
# ---------------------------------------------------------------------------
# Workflow: workflow run analysis
# ---------------------------------------------------------------------------


class TestGetWorkflowRunsByPR:
    def test_returns_filtered_runs(self):
        runs = [
            {"name": "quality-gate", "pull_requests": [{"number": 42}]},
            {"name": "other", "pull_requests": [{"number": 99}]},
        ]
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=json.dumps(runs)),
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
            return_value=_completed(stdout=json.dumps(runs)),
        ):
            result = get_workflow_runs_by_pr(42, workflow_name="quality", repository="o/r")
        assert len(result) == 1

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
