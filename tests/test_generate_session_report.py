"""Tests for generate_session_report.py consumer script."""

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


_mod = _import_script("generate_session_report")
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
    overall_verdict: str = "PASS",
    must_failures: str = "0",
    github_repository: str = "owner/repo",
    server_url: str = "https://github.com",
    run_id: str = "12345",
) -> list[str]:
    return [
        "--overall-verdict", overall_verdict,
        "--must-failures", must_failures,
        "--github-repository", github_repository,
        "--server-url", server_url,
        "--run-id", run_id,
    ]


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("OVERALL_VERDICT", raising=False)
        monkeypatch.delenv("MUST_FAILURES", raising=False)
        args = build_parser().parse_args([])
        assert args.overall_verdict == "PASS"
        assert args.must_failures == "0"

    def test_cli_args(self):
        args = build_parser().parse_args([
            "--overall-verdict", "CRITICAL_FAIL",
            "--must-failures", "5",
        ])
        assert args.overall_verdict == "CRITICAL_FAIL"
        assert args.must_failures == "5"


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_pass_verdict_generates_report(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        monkeypatch.chdir(tmp_path)
        with patch(
            "generate_session_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv())
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert "report_file" in outputs
        report = Path(outputs["report_file"]).read_text()
        assert "Session Protocol Compliance Report" in report
        assert "All session protocol requirements satisfied" in report

    def test_must_failures_message(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        monkeypatch.chdir(tmp_path)
        with patch(
            "generate_session_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv(must_failures="3"))
        assert rc == 0
        report = (report_dir / "session-compliance-report.md").read_text()
        assert "3 MUST requirement(s) not met" in report

    def test_includes_verdict_files_in_table(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        monkeypatch.chdir(tmp_path)

        # Create verdict files
        results_dir = Path("validation-results")
        results_dir.mkdir(parents=True, exist_ok=True)
        (results_dir / "session-1-verdict.txt").write_text("PASS")
        (results_dir / "session-1-must-failures.txt").write_text("0")

        with patch(
            "generate_session_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv())
        assert rc == 0
        report = (report_dir / "session-compliance-report.md").read_text()
        assert "session-1" in report

    def test_includes_findings_details(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        monkeypatch.chdir(tmp_path)

        results_dir = Path("validation-results")
        results_dir.mkdir(parents=True, exist_ok=True)
        (results_dir / "session-1-verdict.txt").write_text("FAIL")
        (results_dir / "session-1-findings.txt").write_text("Missing MUST items")

        with patch(
            "generate_session_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv(overall_verdict="FAIL"))
        assert rc == 0
        report = (report_dir / "session-compliance-report.md").read_text()
        assert "Missing MUST items" in report

    def test_run_details_in_report(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        monkeypatch.chdir(tmp_path)
        with patch(
            "generate_session_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv(run_id="99999"))
        assert rc == 0
        report = (report_dir / "session-compliance-report.md").read_text()
        assert "99999" in report

    def test_non_digit_must_failures_treated_as_zero(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        monkeypatch.chdir(tmp_path)
        with patch(
            "generate_session_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv(must_failures="not-a-number"))
        assert rc == 0
        report = (report_dir / "session-compliance-report.md").read_text()
        assert "All session protocol requirements satisfied" in report
