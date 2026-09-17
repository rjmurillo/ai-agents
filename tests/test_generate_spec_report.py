"""Tests for generate_spec_report.py consumer script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the consumer script via importlib (not a package)
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


_mod = _import_script("generate_spec_report")
main = _mod.main
build_parser = _mod.build_parser
_findings_section = _mod._findings_section

# Realistic infra-failure findings text (issue #5738 follow-up): the fixture
# default ("All traced" / "All complete") never contains "CRITICAL_FAIL", so
# an assertion that CRITICAL_FAIL is absent from the report would pass no
# matter what the code does with it. These strings match the shape
# invoke_copilot_cli.py actually emits on an infra failure (a VERDICT line
# followed by a MESSAGE line), so a mutation that stops labeling the raw
# text is caught.
_INFRA_TRACE_FINDINGS = (
    "VERDICT: CRITICAL_FAIL\n"
    "MESSAGE: Copilot CLI infrastructure failure after 3 attempts: "
    "rate limited (HTTP 429) on the traceability review."
)
_INFRA_COMPLETENESS_FINDINGS = (
    "VERDICT: CRITICAL_FAIL\n"
    "MESSAGE: Copilot CLI infrastructure failure after 3 attempts: "
    "network timeout on the completeness review."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_output(tmp_path: Path, monkeypatch) -> Path:
    output_file = tmp_path / "output"
    output_file.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    return output_file


def _read_outputs(output_file: Path) -> dict[str, str]:
    lines = output_file.read_text().strip().splitlines()
    result = {}
    for line in lines:
        if "=" in line:
            k, v = line.split("=", 1)
            result[k] = v
    return result


def _make_argv(
    has_specs: str = "true",
    trace_verdict: str = "PASS",
    completeness_verdict: str = "PASS",
    spec_refs: str = "REQ-001",
    issue_refs: str = "#42",
    trace_findings: str = "All traced",
    completeness_findings: str = "All complete",
    trace_infra_failure: str = "",
    completeness_infra_failure: str = "",
    github_repository: str = "owner/repo",
    server_url: str = "https://github.com",
    run_id: str = "12345",
    event_name: str = "pull_request",
    ref_name: str = "main",
) -> list[str]:
    return [
        "--has-specs", has_specs,
        "--trace-verdict", trace_verdict,
        "--completeness-verdict", completeness_verdict,
        "--spec-refs", spec_refs,
        "--issue-refs", issue_refs,
        "--trace-findings", trace_findings,
        "--completeness-findings", completeness_findings,
        "--trace-infra-failure", trace_infra_failure,
        "--completeness-infra-failure", completeness_infra_failure,
        "--github-repository", github_repository,
        "--server-url", server_url,
        "--run-id", run_id,
        "--event-name", event_name,
        "--ref-name", ref_name,
    ]


# ---------------------------------------------------------------------------
# Tests: _findings_section (issue #5738 follow-up)
# ---------------------------------------------------------------------------


class TestFindingsSection:
    def test_non_infra_returns_findings_unchanged(self):
        """Positive: the healthy-side path is untouched by the label logic."""
        assert _findings_section(False, "All traced") == "All traced"

    def test_infra_prefixes_label_before_raw_text(self):
        """Edge: an infra-flagged side keeps the raw text but labels it,
        with the label appearing before the raw text, not replacing it."""
        raw = "VERDICT: CRITICAL_FAIL\nMESSAGE: boom"
        result = _findings_section(True, raw)
        assert "This check did not run (infrastructure failure)" in result
        assert raw in result
        assert result.index("This check did not run") < result.index(raw)

    def test_infra_with_empty_findings_still_labels(self):
        """Negative: even empty findings text gets the label, not silence."""
        result = _findings_section(True, "")
        assert "This check did not run (infrastructure failure)" in result


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_all_args_parsed(self):
        args = build_parser().parse_args(_make_argv())
        assert args.has_specs == "true"
        assert args.trace_verdict == "PASS"
        assert args.completeness_verdict == "PASS"
        assert args.trace_infra_failure == ""
        assert args.completeness_infra_failure == ""

    def test_infra_failure_args_parsed(self):
        args = build_parser().parse_args(_make_argv(
            trace_infra_failure="true",
            completeness_infra_failure="true",
        ))
        assert args.trace_infra_failure == "true"
        assert args.completeness_infra_failure == "true"

    def test_defaults_to_empty(self, monkeypatch):
        for env in ["HAS_SPECS", "SPEC_REFS", "ISSUE_REFS", "TRACE_VERDICT",
                     "TRACE_FINDINGS", "COMPLETENESS_VERDICT", "COMPLETENESS_FINDINGS",
                     "TRACE_INFRA_FAILURE", "COMPLETENESS_INFRA_FAILURE",
                     "GITHUB_REPOSITORY", "SERVER_URL", "RUN_ID", "EVENT_NAME",
                     "REF_NAME"]:
            monkeypatch.delenv(env, raising=False)
        args = build_parser().parse_args([])
        assert args.has_specs == ""


# ---------------------------------------------------------------------------
# Tests: main - no specs
# ---------------------------------------------------------------------------


class TestMainNoSpecs:
    def test_no_specs_generates_warning_report(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch(
            "generate_spec_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv(has_specs="false"))
        assert rc == 0
        outputs = _read_outputs(output_file)
        report = Path(outputs["report_file"]).read_text()
        assert "No spec references found" in report
        assert "How to add spec references" in report


# ---------------------------------------------------------------------------
# Tests: main - with specs
# ---------------------------------------------------------------------------


class TestMainWithSpecs:
    def test_all_pass_generates_pass_report(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch(
            "generate_spec_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv())
        assert rc == 0
        report = (report_dir / "spec-validation-report.md").read_text()
        assert "Final Verdict: PASS" in report

    def test_trace_fail_generates_fail_report(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch(
            "generate_spec_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv(trace_verdict="FAIL"))
        assert rc == 0
        report = (report_dir / "spec-validation-report.md").read_text()
        assert "Final Verdict: FAIL" in report

    def test_warn_verdict_propagated(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch(
            "generate_spec_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv(trace_verdict="WARN"))
        assert rc == 0
        report = (report_dir / "spec-validation-report.md").read_text()
        assert "Final Verdict: WARN" in report

    def test_report_includes_spec_refs(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch(
            "generate_spec_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv(spec_refs="REQ-001 REQ-002"))
        assert rc == 0
        report = (report_dir / "spec-validation-report.md").read_text()
        assert "REQ-001 REQ-002" in report

    def test_empty_spec_refs_shows_none(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch(
            "generate_spec_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv(spec_refs="", issue_refs=""))
        assert rc == 0
        report = (report_dir / "spec-validation-report.md").read_text()
        assert "*None*" in report

    def test_report_includes_findings(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch(
            "generate_spec_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv(
                trace_findings="Trace details here",
                completeness_findings="Completeness details here",
            ))
        assert rc == 0
        report = (report_dir / "spec-validation-report.md").read_text()
        assert "Trace details here" in report
        assert "Completeness details here" in report

    def test_run_details_included(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch(
            "generate_spec_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv(run_id="99999"))
        assert rc == 0
        report = (report_dir / "spec-validation-report.md").read_text()
        assert "99999" in report


# ---------------------------------------------------------------------------
# Tests: main - infrastructure failure (issue #5738)
#
# check_spec_failures.py governs whether the required check blocks merge;
# these tests govern the separate, non-blocking PR comment channel that
# operators actually read. Before this fix, an infra failure rendered the
# raw AI-review verdict (CRITICAL_FAIL) unlabeled, indistinguishable from a
# real code-quality rejection.
# ---------------------------------------------------------------------------


class TestMainInfraFailure:
    def test_both_infra_failures_yield_infra_failure_verdict(self, tmp_path, monkeypatch):
        """Positive: both sides failing on infra never reads as PASS or FAIL,
        the summary table never shows a bare CRITICAL_FAIL cell, and the raw
        Copilot CLI output survives (labeled) instead of being deleted."""
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch(
            "generate_spec_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv(
                trace_verdict="CRITICAL_FAIL",
                completeness_verdict="CRITICAL_FAIL",
                trace_infra_failure="true",
                completeness_infra_failure="true",
                trace_findings=_INFRA_TRACE_FINDINGS,
                completeness_findings=_INFRA_COMPLETENESS_FINDINGS,
            ))
        assert rc == 0
        report = (report_dir / "spec-validation-report.md").read_text()
        assert "Final Verdict: INFRA_FAILURE" in report
        assert "Final Verdict: FAIL" not in report
        assert "Final Verdict: PASS" not in report
        assert "does not block merge" in report
        # The summary table cell is the displayed verdict an operator scans;
        # it must show the honest label, never the bare raw verdict.
        assert "| Requirements Traceability | `INFRA_FAILURE (did not run)` |" in report
        assert "| Implementation Completeness | `INFRA_FAILURE (did not run)` |" in report
        assert "| Requirements Traceability | `CRITICAL_FAIL` |" not in report
        assert "| Implementation Completeness | `CRITICAL_FAIL` |" not in report
        assert "COPILOT_GITHUB_TOKEN" in report
        assert "infrastructure failure" in report.lower()
        # Observability (issue #5738 follow-up): the raw Copilot CLI output
        # is retained, not deleted, but only inside its side's own labeled
        # details block, after the "did not run" label, never as a bare
        # verdict line ahead of it.
        assert report.count("This check did not run (infrastructure failure)") == 2
        trace_label_index = report.index("This check did not run (infrastructure failure)")
        trace_raw_index = report.index("rate limited (HTTP 429) on the traceability review")
        assert trace_label_index < trace_raw_index
        completeness_label_index = report.rindex(
            "This check did not run (infrastructure failure)"
        )
        completeness_raw_index = report.index(
            "network timeout on the completeness review"
        )
        assert completeness_label_index < completeness_raw_index

    def test_real_failure_not_masked_by_infra_on_other_side(self, tmp_path, monkeypatch):
        """Negative: a genuine failure on the healthy side still surfaces as
        FAIL, and the infra note must not claim this does not block merge
        (Additional Finding 3: a FAIL from the healthy side is real and
        blocks under check_spec_failures.py's own policy)."""
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch(
            "generate_spec_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv(
                trace_verdict="CRITICAL_FAIL",
                completeness_verdict="FAIL",
                trace_infra_failure="true",
                trace_findings=_INFRA_TRACE_FINDINGS,
            ))
        assert rc == 0
        report = (report_dir / "spec-validation-report.md").read_text()
        assert "Final Verdict: FAIL" in report
        assert "Final Verdict: INFRA_FAILURE" not in report
        assert "does not block merge" not in report
        assert "blocks merge under normal policy" in report

    def test_one_sided_infra_failure_yields_warn_not_pass(self, tmp_path, monkeypatch):
        """Edge: one side down and the other healthy is WARN, not a clean
        PASS, and the summary table's own cell (not the boilerplate note
        text) is what proves the infra side is labeled."""
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch(
            "generate_spec_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv(
                trace_verdict="CRITICAL_FAIL",
                completeness_verdict="PASS",
                trace_infra_failure="true",
                trace_findings=_INFRA_TRACE_FINDINGS,
            ))
        assert rc == 0
        report = (report_dir / "spec-validation-report.md").read_text()
        assert "Final Verdict: WARN" in report
        assert "Final Verdict: PASS" not in report
        assert "does not block merge" in report
        assert "| Requirements Traceability | `INFRA_FAILURE (did not run)` |" in report
        assert "| Requirements Traceability | `CRITICAL_FAIL` |" not in report
        assert "| Implementation Completeness | `PASS` |" in report

    def test_no_infra_flags_preserves_prior_pass_behavior(self, tmp_path, monkeypatch):
        """Negative control: default (no infra flags) is unaffected by this change."""
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch(
            "generate_spec_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv())
        assert rc == 0
        report = (report_dir / "spec-validation-report.md").read_text()
        assert "Final Verdict: PASS" in report
        assert "INFRA_FAILURE" not in report
        assert "Infrastructure failure detected" not in report


def test_main_rejects_an_unrecognized_flag() -> None:
    """Every argument here has a default, so a typo'd flag is the CLI's only
    reachable failure path. Argparse's own rejection proves the exit contract:
    the workflow step exits nonzero instead of silently ignoring the typo.
    """
    with pytest.raises(SystemExit) as excinfo:
        main(["--this-flag-does-not-exist"])

    assert excinfo.value.code != 0
