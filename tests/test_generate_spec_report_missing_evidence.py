"""Tests: a spec review side with no evidence never reads as PASS (issue #6182)."""

from __future__ import annotations

from unittest.mock import patch

from generate_spec_report import main

from tests.test_generate_spec_report import _make_argv, _setup_output


class TestMissingEvidenceIsNeverPass:
    def _report(self, tmp_path, monkeypatch, **kwargs) -> str:
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch(
            "generate_spec_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            assert main(_make_argv(**kwargs)) == 0
        return (report_dir / "spec-validation-report.md").read_text()

    def test_crashed_trace_step_with_no_outputs(self, tmp_path, monkeypatch):
        report = self._report(
            tmp_path,
            monkeypatch,
            trace_verdict="",
            trace_findings="",
            trace_outcome="failure",
            completeness_verdict="PASS",
            completeness_outcome="success",
        )
        assert "Final Verdict: INFRA_FAILURE" in report
        assert "Final Verdict: PASS" not in report
        assert "| Requirements Traceability | `INFRA_FAILURE (did not run)` |" in report
        assert "| Implementation Completeness | `PASS` |" in report

    def test_crashed_completeness_step_with_no_outputs(self, tmp_path, monkeypatch):
        report = self._report(
            tmp_path,
            monkeypatch,
            trace_verdict="PASS",
            trace_outcome="success",
            completeness_verdict="",
            completeness_findings="",
            completeness_outcome="failure",
        )
        assert "Final Verdict: INFRA_FAILURE" in report
        assert "Final Verdict: PASS" not in report
        assert "| Implementation Completeness | `INFRA_FAILURE (did not run)` |" in report

    def test_both_sides_empty_even_without_outcomes(self, tmp_path, monkeypatch):
        report = self._report(
            tmp_path,
            monkeypatch,
            trace_verdict="",
            completeness_verdict="",
        )
        assert "Final Verdict: INFRA_FAILURE" in report
        assert "Final Verdict: PASS" not in report

    def test_non_success_outcome_beats_a_stale_verdict(self, tmp_path, monkeypatch):
        report = self._report(
            tmp_path,
            monkeypatch,
            trace_verdict="PASS",
            trace_outcome="cancelled",
            completeness_verdict="PASS",
            completeness_outcome="success",
        )
        assert "Final Verdict: PASS" not in report
        assert "| Requirements Traceability | `INFRA_FAILURE (did not run)` |" in report

    def test_a_real_fail_on_the_other_side_still_reports_fail(self, tmp_path, monkeypatch):
        report = self._report(
            tmp_path,
            monkeypatch,
            trace_verdict="",
            trace_outcome="failure",
            completeness_verdict="CRITICAL_FAIL",
            completeness_outcome="success",
        )
        assert "Final Verdict: FAIL" in report

    def test_normal_pass_control_with_success_outcomes(self, tmp_path, monkeypatch):
        report = self._report(
            tmp_path,
            monkeypatch,
            trace_outcome="success",
            completeness_outcome="success",
        )
        assert "Final Verdict: PASS" in report
        assert "did not run" not in report

    def test_no_specs_report_ignores_empty_verdicts(self, tmp_path, monkeypatch):
        report = self._report(
            tmp_path,
            monkeypatch,
            has_specs="false",
            trace_verdict="",
            completeness_verdict="",
        )
        assert "INFRA_FAILURE" not in report
