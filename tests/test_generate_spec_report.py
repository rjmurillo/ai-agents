"""Tests for generate_spec_report.py consumer script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Import the consumer script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("generate_spec_report")
main = _mod.main
build_parser = _mod.build_parser

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
        "--github-repository", github_repository,
        "--server-url", server_url,
        "--run-id", run_id,
        "--event-name", event_name,
        "--ref-name", ref_name,
    ]


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_all_args_parsed(self):
        args = build_parser().parse_args(_make_argv())
        assert args.has_specs == "true"
        assert args.trace_verdict == "PASS"
        assert args.completeness_verdict == "PASS"

    def test_defaults_to_empty(self, monkeypatch):
        for env in ["HAS_SPECS", "SPEC_REFS", "ISSUE_REFS", "TRACE_VERDICT",
                     "TRACE_FINDINGS", "COMPLETENESS_VERDICT", "COMPLETENESS_FINDINGS",
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
