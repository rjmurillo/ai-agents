"""Tests for measure_workflow_coalescing.py."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC
from pathlib import Path
from typing import Any
from unittest.mock import patch

from scripts.github_core.api import RepoInfo

# ---------------------------------------------------------------------------
# Import the script via importlib (same pattern as test_invoke_pr_maintenance.py)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None, f"Could not load spec for {name}"
    assert spec.loader is not None, f"Spec for {name} has no loader"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("measure_workflow_coalescing")
WorkflowRun = _mod.WorkflowRun
RunOverlap = _mod.RunOverlap
CoalescingMetrics = _mod.CoalescingMetrics
check_runs_overlap = _mod.check_runs_overlap
get_overlapping_runs = _mod.get_overlapping_runs
get_coalescing_metrics = _mod.get_coalescing_metrics
get_concurrency_group = _mod.get_concurrency_group
format_markdown_report = _mod.format_markdown_report
main = _mod.main
DEFAULT_WORKFLOWS = _mod.DEFAULT_WORKFLOWS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(
    id: int = 1,
    name: str = "ai-pr-quality-gate",
    created_at: str = "2026-01-01T10:00:00Z",
    updated_at: str = "2026-01-01T10:05:00Z",
    conclusion: str | None = "success",
    event: str = "pull_request",
    head_branch: str = "feature-branch",
    pull_requests: list[dict] | None = None,
) -> Any:
    if pull_requests is None:
        pull_requests = [{"number": 123}]
    return WorkflowRun(
        id=id,
        name=name,
        created_at=created_at,
        updated_at=updated_at,
        conclusion=conclusion,
        event=event,
        head_branch=head_branch,
        pull_requests=pull_requests,
    )


# ---------------------------------------------------------------------------
# Tests: Overlap Detection
# ---------------------------------------------------------------------------


class TestOverlapDetection:
    def test_detects_overlapping_runs(self):
        run1 = _make_run(id=1, created_at="2026-01-01T10:00:00Z", updated_at="2026-01-01T10:05:00Z")
        run2 = _make_run(id=2, created_at="2026-01-01T10:03:00Z", updated_at="2026-01-01T10:08:00Z")
        assert check_runs_overlap(run1, run2) is True

    def test_treats_equal_start_time_as_overlap(self):
        run1 = _make_run(id=1, created_at="2026-01-01T10:00:00Z", updated_at="2026-01-01T10:05:00Z")
        run2 = _make_run(id=2, created_at="2026-01-01T10:00:00Z", updated_at="2026-01-01T10:06:00Z")
        assert check_runs_overlap(run1, run2) is True

    def test_does_not_detect_non_overlapping_runs(self):
        run1 = _make_run(id=1, created_at="2026-01-01T10:00:00Z", updated_at="2026-01-01T10:05:00Z")
        run2 = _make_run(id=2, created_at="2026-01-01T10:06:00Z", updated_at="2026-01-01T10:10:00Z")
        assert check_runs_overlap(run1, run2) is False

    def test_run2_starts_before_run1_finishes(self):
        run1 = _make_run(
            id=1,
            created_at="2026-01-01T10:00:00Z",
            updated_at="2026-01-01T10:10:00Z",
            conclusion="cancelled",
        )
        run2 = _make_run(
            id=2,
            created_at="2026-01-01T10:02:00Z",
            updated_at="2026-01-01T10:12:00Z",
            conclusion="success",
        )
        assert check_runs_overlap(run1, run2) is True


# ---------------------------------------------------------------------------
# Tests: Cancellation Detection
# ---------------------------------------------------------------------------


class TestCancellationDetection:
    def test_identifies_cancelled_runs_in_overlap(self):
        run1 = _make_run(
            id=1,
            created_at="2026-01-01T10:00:00Z",
            updated_at="2026-01-01T10:05:00Z",
            conclusion="cancelled",
        )
        run2 = _make_run(
            id=2,
            created_at="2026-01-01T10:03:00Z",
            updated_at="2026-01-01T10:08:00Z",
            conclusion="success",
        )

        overlaps = get_overlapping_runs([run1, run2])

        assert len(overlaps) == 1
        assert overlaps[0].run1_cancelled is True
        assert overlaps[0].is_race_condition is False

    def test_identifies_race_condition(self):
        run1 = _make_run(
            id=1,
            created_at="2026-01-01T10:00:00Z",
            updated_at="2026-01-01T10:05:00Z",
            conclusion="success",
        )
        run2 = _make_run(
            id=2,
            created_at="2026-01-01T10:03:00Z",
            updated_at="2026-01-01T10:08:00Z",
            conclusion="success",
        )

        overlaps = get_overlapping_runs([run1, run2])

        assert len(overlaps) == 1
        assert overlaps[0].run1_cancelled is False
        assert overlaps[0].run2_cancelled is False
        assert overlaps[0].is_race_condition is True


# ---------------------------------------------------------------------------
# Tests: Metrics Calculation
# ---------------------------------------------------------------------------


class TestMetricsCalculation:
    def test_90_percent_effectiveness(self):
        runs = [
            _make_run(id=i, conclusion="cancelled")
            for i in range(1, 10)
        ] + [_make_run(id=10, conclusion="success")]

        overlaps = [
            RunOverlap(
                concurrency_group="g",
                run1=_make_run(id=i),
                run2=_make_run(id=i + 1),
                run1_cancelled=True,
                run2_cancelled=False,
                is_race_condition=False,
            )
            for i in range(1, 10)
        ] + [
            RunOverlap(
                concurrency_group="g",
                run1=_make_run(id=10),
                run2=_make_run(id=11),
                run1_cancelled=False,
                run2_cancelled=False,
                is_race_condition=True,
            )
        ]

        metrics = get_coalescing_metrics(runs, overlaps)

        assert metrics.coalescing_effectiveness == 90.0
        assert metrics.successful_coalescing == 9
        assert metrics.race_conditions == 1

    def test_zero_runs_gracefully(self):
        metrics = get_coalescing_metrics([], [])

        assert metrics.total_runs == 0
        assert metrics.coalescing_effectiveness == 0.0
        assert metrics.race_condition_rate == 0.0

    def test_100_percent_effectiveness(self):
        runs = [
            _make_run(id=1, conclusion="cancelled"),
            _make_run(id=2, conclusion="success"),
        ]

        overlaps = [
            RunOverlap(
                concurrency_group="g",
                run1=_make_run(id=1),
                run2=_make_run(id=2),
                run1_cancelled=True,
                run2_cancelled=False,
                is_race_condition=False,
            )
        ]

        metrics = get_coalescing_metrics(runs, overlaps)

        assert metrics.coalescing_effectiveness == 100.0
        assert metrics.race_conditions == 0


# ---------------------------------------------------------------------------
# Tests: Concurrency Group Extraction
# ---------------------------------------------------------------------------


class TestConcurrencyGroupExtraction:
    def test_quality_workflow_pr(self):
        run = _make_run(
            name="ai-pr-quality-gate",
            event="pull_request",
            pull_requests=[{"number": 123}],
        )
        assert get_concurrency_group(run) == "ai-quality-123"

    def test_spec_validation_pr(self):
        run = _make_run(
            name="ai-spec-validation",
            event="pull_request",
            pull_requests=[{"number": 456}],
        )
        assert get_concurrency_group(run) == "spec-validation-456"

    def test_non_pr_fallback(self):
        run = _make_run(
            name="ai-pr-quality-gate",
            event="push",
            pull_requests=[],
            head_branch="main",
        )
        assert get_concurrency_group(run) == "ai-pr-quality-gate-main"

    def test_session_workflow_pr(self):
        run = _make_run(
            name="ai-session-protocol",
            event="pull_request",
            pull_requests=[{"number": 789}],
        )
        assert get_concurrency_group(run) == "session-protocol-789"

    def test_label_workflow_pr(self):
        run = _make_run(
            name="label-pr",
            event="pull_request",
            pull_requests=[{"number": 100}],
        )
        assert get_concurrency_group(run) == "label-pr-100"

    def test_memory_workflow_pr(self):
        run = _make_run(
            name="memory-validation",
            event="pull_request",
            pull_requests=[{"number": 200}],
        )
        assert get_concurrency_group(run) == "memory-validation-200"

    def test_assign_workflow_pr(self):
        run = _make_run(
            name="auto-assign-reviewer",
            event="pull_request",
            pull_requests=[{"number": 300}],
        )
        assert get_concurrency_group(run) == "auto-assign-300"

    def test_default_pr_validation(self):
        run = _make_run(
            name="pr-validation",
            event="pull_request",
            pull_requests=[{"number": 400}],
        )
        assert get_concurrency_group(run) == "pr-validation-400"


# ---------------------------------------------------------------------------
# Tests: Report Generation
# ---------------------------------------------------------------------------


class TestReportGeneration:
    def test_generates_valid_markdown_structure(self):
        from datetime import datetime

        metrics = CoalescingMetrics(
            total_runs=100,
            cancelled_runs=45,
            race_conditions=5,
            successful_coalescing=40,
            coalescing_effectiveness=88.89,
            race_condition_rate=5.0,
            avg_cancellation_time=3.5,
        )

        runs = [
            _make_run(
                name="ai-pr-quality-gate",
                conclusion="success",
                created_at="2026-01-01T10:00:00Z",
                updated_at="2026-01-01T10:05:00Z",
            )
        ]

        overlaps: list[Any] = []
        workflows = ["ai-pr-quality-gate", "ai-spec-validation"]
        start_date = datetime(2026, 1, 1, tzinfo=UTC)
        end_date = datetime(2026, 1, 31, tzinfo=UTC)

        report = format_markdown_report(
            metrics, runs, overlaps, start_date, end_date, workflows,
        )

        assert "# Workflow Run Coalescing Metrics" in report
        assert "## Report Period" in report
        assert "## Executive Summary" in report
        assert "Coalescing Effectiveness" in report
        assert "88.89%" in report

    def test_race_condition_details_included(self):
        from datetime import datetime

        metrics = CoalescingMetrics(
            total_runs=10,
            cancelled_runs=3,
            race_conditions=2,
            successful_coalescing=3,
            coalescing_effectiveness=60.0,
            race_condition_rate=20.0,
            avg_cancellation_time=2.0,
        )

        r1 = _make_run(id=100)
        r2 = _make_run(id=200)
        overlaps = [
            RunOverlap(
                concurrency_group="test-group",
                run1=r1,
                run2=r2,
                run1_cancelled=False,
                run2_cancelled=False,
                is_race_condition=True,
            )
        ]

        report = format_markdown_report(
            metrics,
            [r1, r2],
            overlaps,
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 31, tzinfo=UTC),
            ["test-workflow"],
        )

        assert "## Race Condition Details" in report
        assert "100" in report
        assert "200" in report

    def test_recommendations_high_race_rate(self):
        from datetime import datetime

        metrics = CoalescingMetrics(
            total_runs=10,
            cancelled_runs=2,
            race_conditions=5,
            successful_coalescing=2,
            coalescing_effectiveness=28.57,
            race_condition_rate=50.0,
            avg_cancellation_time=2.0,
        )

        report = format_markdown_report(
            metrics, [], [], datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 31, tzinfo=UTC), ["test"],
        )

        assert "HIGH PRIORITY" in report
        assert "50.0%" in report

    def test_recommendations_all_on_track(self):
        from datetime import datetime

        metrics = CoalescingMetrics(
            total_runs=100,
            cancelled_runs=50,
            race_conditions=2,
            successful_coalescing=48,
            coalescing_effectiveness=96.0,
            race_condition_rate=2.0,
            avg_cancellation_time=3.0,
        )

        report = format_markdown_report(
            metrics, [], [], datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 31, tzinfo=UTC), ["test"],
        )

        assert "All metrics are within target thresholds" in report

    def test_generated_by_line(self):
        from datetime import datetime

        metrics = CoalescingMetrics(
            total_runs=0, cancelled_runs=0, race_conditions=0,
            successful_coalescing=0, coalescing_effectiveness=0.0,
            race_condition_rate=0.0, avg_cancellation_time=0.0,
        )

        report = format_markdown_report(
            metrics, [], [], datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 31, tzinfo=UTC), [],
        )

        assert "measure_workflow_coalescing.py" in report


# ---------------------------------------------------------------------------
# Tests: WorkflowRun dataclass
# ---------------------------------------------------------------------------


class TestWorkflowRun:
    def test_from_api(self):
        data = {
            "id": 42,
            "name": "test-workflow",
            "created_at": "2026-01-01T10:00:00Z",
            "updated_at": "2026-01-01T10:05:00Z",
            "conclusion": "success",
            "event": "push",
            "head_branch": "main",
            "pull_requests": [{"number": 1}],
        }
        run = WorkflowRun.from_api(data)
        assert run.id == 42
        assert run.name == "test-workflow"
        assert run.conclusion == "success"
        assert run.event == "push"
        assert run.head_branch == "main"
        assert len(run.pull_requests) == 1

    def test_from_api_missing_fields(self):
        run = WorkflowRun.from_api({})
        assert run.id == 0
        assert run.name == ""
        assert run.conclusion is None
        assert run.pull_requests == []

    def test_datetime_parsing(self):
        run = _make_run(
            created_at="2026-01-15T08:30:00Z",
            updated_at="2026-01-15T08:35:00Z",
        )
        assert run.created_dt.year == 2026
        assert run.created_dt.month == 1
        assert run.created_dt.day == 15
        assert run.created_dt.hour == 8
        assert run.created_dt.minute == 30
        elapsed = (run.updated_dt - run.created_dt).total_seconds()
        assert elapsed == 300.0


# ---------------------------------------------------------------------------
# Tests: Main function
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_no_runs_exits_0(self):
        with patch(
            "measure_workflow_coalescing.test_prerequisites",
        ), patch(
            "measure_workflow_coalescing.get_repository_context",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "measure_workflow_coalescing.get_workflow_runs",
            return_value=[],
        ):
            rc = main(["--since", "7", "--repository", "o/r"])
        assert rc == 0

    def test_main_json_output(self, tmp_path):
        runs = [_make_run(id=1, conclusion="success")]
        output_file = tmp_path / "out.json"

        with patch(
            "measure_workflow_coalescing.test_prerequisites",
        ), patch(
            "measure_workflow_coalescing.get_repository_context",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "measure_workflow_coalescing.get_workflow_runs",
            return_value=runs,
        ):
            rc = main([
                "--since", "7",
                "--repository", "o/r",
                "--output", "json",
                "--output-path", str(output_file),
            ])

        assert rc == 0
        assert output_file.exists()
        import json
        data = json.loads(output_file.read_text())
        assert "Metrics" in data
        assert data["Runs"] == 1

    def test_main_markdown_output(self, tmp_path):
        runs = [_make_run(id=1, conclusion="cancelled")]
        output_file = tmp_path / "report.md"

        with patch(
            "measure_workflow_coalescing.test_prerequisites",
        ), patch(
            "measure_workflow_coalescing.get_repository_context",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "measure_workflow_coalescing.get_workflow_runs",
            return_value=runs,
        ):
            rc = main([
                "--since", "7",
                "--repository", "o/r",
                "--output", "markdown",
                "--output-path", str(output_file),
            ])

        assert rc == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "# Workflow Run Coalescing Metrics" in content

    def test_main_error_exits_1(self):
        with patch(
            "measure_workflow_coalescing.test_prerequisites",
            side_effect=RuntimeError("gh not found"),
        ):
            rc = main(["--repository", "o/r"])
        assert rc == 1

    def test_main_summary_output(self):
        runs = [_make_run(id=1, conclusion="success")]

        with patch(
            "measure_workflow_coalescing.test_prerequisites",
        ), patch(
            "measure_workflow_coalescing.get_repository_context",
            return_value=RepoInfo(owner="o", repo="r"),
        ), patch(
            "measure_workflow_coalescing.get_workflow_runs",
            return_value=runs,
        ):
            rc = main([
                "--since", "7",
                "--repository", "o/r",
                "--output", "summary",
            ])

        assert rc == 0


# ---------------------------------------------------------------------------
# Tests: Default workflows list
# ---------------------------------------------------------------------------


class TestDefaultWorkflows:
    def test_default_workflows_contains_expected(self):
        assert "ai-pr-quality-gate" in DEFAULT_WORKFLOWS
        assert "ai-spec-validation" in DEFAULT_WORKFLOWS
        assert "codeql-analysis" in DEFAULT_WORKFLOWS

    def test_default_workflows_count(self):
        assert len(DEFAULT_WORKFLOWS) == 8
