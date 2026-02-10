"""Tests for generate_quality_report.py consumer script."""

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
    assert spec is not None, f"Could not load spec for {name}"
    assert spec.loader is not None, f"Spec for {name} has no loader"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("generate_quality_report")
main = _mod.main
build_parser = _mod.build_parser
_AGENTS = _mod._AGENTS
_AGENT_DISPLAY_NAMES = _mod._AGENT_DISPLAY_NAMES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_argv(
    final_verdict: str = "PASS",
    verdicts: dict[str, str] | None = None,
    categories: dict[str, str] | None = None,
    run_id: str = "12345",
    server_url: str = "https://github.com",
    repository: str = "owner/repo",
    event_name: str = "pull_request",
    ref_name: str = "main",
    sha: str = "abc123",
) -> list[str]:
    argv = [
        "--run-id", run_id,
        "--server-url", server_url,
        "--repository", repository,
        "--event-name", event_name,
        "--ref-name", ref_name,
        "--sha", sha,
        "--final-verdict", final_verdict,
    ]
    verdicts = verdicts or {}
    categories = categories or {}
    for agent in _AGENTS:
        argv.extend([f"--{agent}-verdict", verdicts.get(agent, "PASS")])
        argv.extend([f"--{agent}-category", categories.get(agent, "N/A")])
    return argv


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


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_parses_all_fields(self):
        argv = _make_argv()
        args = build_parser().parse_args(argv)
        assert args.run_id == "12345"
        assert args.final_verdict == "PASS"
        assert args.security_verdict == "PASS"

    def test_defaults_to_empty(self, monkeypatch):
        for env in ["RUN_ID", "SERVER_URL", "REPOSITORY", "EVENT_NAME",
                     "REF_NAME", "SHA", "FINAL_VERDICT"]:
            monkeypatch.delenv(env, raising=False)
        for agent in _AGENTS:
            monkeypatch.delenv(f"{agent.upper()}_VERDICT", raising=False)
            monkeypatch.delenv(f"{agent.upper()}_CATEGORY", raising=False)
        args = build_parser().parse_args([])
        assert args.run_id == ""


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_generates_report_file(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch(
            "generate_quality_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv())
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert "report_file" in outputs
        report_path = Path(outputs["report_file"])
        assert report_path.exists()
        content = report_path.read_text()
        assert "AI Quality Gate Review" in content

    def test_report_contains_agent_table(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        verdicts = {"security": "FAIL", "qa": "PASS"}
        categories = {"security": "CODE_QUALITY", "qa": "N/A"}
        with patch(
            "generate_quality_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv(
                final_verdict="FAIL",
                verdicts=verdicts,
                categories=categories,
            ))
        assert rc == 0
        report = (report_dir / "pr-quality-report.md").read_text()
        assert "| Security |" in report
        assert "| QA |" in report

    def test_report_contains_run_details(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch(
            "generate_quality_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True)
            rc = main(_make_argv(run_id="99999", sha="deadbeef"))
        assert rc == 0
        report = (report_dir / "pr-quality-report.md").read_text()
        assert "99999" in report
        assert "deadbeef" in report

    def test_returns_1_when_report_dir_fails(self, tmp_path, monkeypatch, capsys):
        _setup_output(tmp_path, monkeypatch)
        with patch(
            "generate_quality_report.initialize_ai_review",
            return_value="/nonexistent/dir",
        ):
            rc = main(_make_argv())
        assert rc == 1

    def test_findings_section_included_when_file_exists(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        report_dir.mkdir(parents=True)
        findings_dir = Path("ai-review-results")
        # Create findings in CWD-relative path that the script expects
        monkeypatch.chdir(tmp_path)
        findings_dir.mkdir(parents=True, exist_ok=True)
        (findings_dir / "security-findings.txt").write_text("Found XSS issue")
        with patch(
            "generate_quality_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            rc = main(_make_argv())
        assert rc == 0
        report = (report_dir / "pr-quality-report.md").read_text()
        assert "Found XSS issue" in report

    def test_findings_section_shows_warning_when_missing(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        report_dir.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        with patch(
            "generate_quality_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            rc = main(_make_argv())
        assert rc == 0
        report = (report_dir / "pr-quality-report.md").read_text()
        assert "Findings file not found" in report
