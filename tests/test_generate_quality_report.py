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
_build_action_required_section = _mod._build_action_required_section
_build_findings_sections = _mod._build_findings_sections
_security_review_ran = _mod._security_review_ran

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
    pr_author: str = "",
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
    if pr_author:
        argv.extend(["--pr-author", pr_author])
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
            monkeypatch.delenv(f"{_mod.agent_env_name(agent)}_VERDICT", raising=False)
            monkeypatch.delenv(f"{_mod.agent_env_name(agent)}_CATEGORY", raising=False)
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
        assert "| Reliability |" in report
        assert "| Observability |" in report
        assert "| Agent Safety |" in report
        assert "| Decision Rigor |" in report

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

    def test_action_required_section_with_failures(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        report_dir.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        verdicts = {"security": "CRITICAL_FAIL", "qa": "PASS"}
        with patch(
            "generate_quality_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            rc = main(_make_argv(
                final_verdict="CRITICAL_FAIL",
                verdicts=verdicts,
                pr_author="copilot-swe-agent",
            ))
        assert rc == 0
        report = (report_dir / "pr-quality-report.md").read_text()
        assert "@copilot-swe-agent" in report
        assert "Action Required" in report
        assert "**Security** review flagged issues" in report

    def test_no_action_required_when_all_pass(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        report_dir.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        with patch(
            "generate_quality_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            rc = main(_make_argv(pr_author="some-user"))
        assert rc == 0
        report = (report_dir / "pr-quality-report.md").read_text()
        assert "Action Required" not in report

    def test_no_action_required_when_no_author(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        report_dir.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        verdicts = {"security": "CRITICAL_FAIL"}
        with patch(
            "generate_quality_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            rc = main(_make_argv(
                final_verdict="CRITICAL_FAIL",
                verdicts=verdicts,
            ))
        assert rc == 0
        report = (report_dir / "pr-quality-report.md").read_text()
        assert "Action Required" not in report


# ---------------------------------------------------------------------------
# Tests: _build_action_required_section (unit)
# ---------------------------------------------------------------------------


class TestBuildActionRequiredSection:
    def test_returns_empty_when_no_author(self):
        result = _build_action_required_section(
            "", "FAIL", {"security": "FAIL"}, {"security": "CODE_QUALITY"}
        )
        assert result == ""

    def test_returns_empty_when_no_failures(self):
        result = _build_action_required_section(
            "user",
            "PASS",
            {a: "PASS" for a in _AGENTS},
            {a: "N/A" for a in _AGENTS},
        )
        assert result == ""

    def test_mentions_author_on_critical_fail(self):
        verdicts = {a: "PASS" for a in _AGENTS}
        verdicts["security"] = "CRITICAL_FAIL"
        categories = {a: "CODE_QUALITY" for a in _AGENTS}
        result = _build_action_required_section(
            "bot-user", "CRITICAL_FAIL", verdicts, categories
        )
        assert "@bot-user" in result
        assert "**Security** review flagged issues" in result

    def test_lists_multiple_failed_agents(self):
        verdicts = {a: "PASS" for a in _AGENTS}
        verdicts["security"] = "FAIL"
        verdicts["qa"] = "NEEDS_REVIEW"
        categories = {a: "CODE_QUALITY" for a in _AGENTS}
        result = _build_action_required_section("author", "FAIL", verdicts, categories)
        assert "**Security**" in result
        assert "**QA**" in result
        assert "**Analyst**" not in result

    def test_excludes_infrastructure_failed_agent(self):
        # An agent that never ran receives category INFRASTRUCTURE. It must not
        # appear in Action Required (issue #2818).
        verdicts = {a: "PASS" for a in _AGENTS}
        verdicts["security"] = "NEEDS_REVIEW"
        categories = {a: "N/A" for a in _AGENTS}
        categories["security"] = "INFRASTRUCTURE"
        result = _build_action_required_section(
            "author", "WARN", verdicts, categories
        )
        assert result == ""

    def test_lists_real_failure_but_not_infra_failure(self):
        verdicts = {a: "PASS" for a in _AGENTS}
        verdicts["qa"] = "FAIL"
        verdicts["security"] = "NEEDS_REVIEW"
        categories = {a: "N/A" for a in _AGENTS}
        categories["qa"] = "CODE_QUALITY"
        categories["security"] = "INFRASTRUCTURE"
        result = _build_action_required_section("author", "FAIL", verdicts, categories)
        assert "**QA** review flagged issues" in result
        assert "**Security**" not in result


# ---------------------------------------------------------------------------
# Tests: security did-not-run notice (issue #4777)
# ---------------------------------------------------------------------------


class TestSecurityNotice:
    """The report renders a distinct CAUTION block when the security axis hit
    an infrastructure failure (issue #4777)."""

    def _render(self, tmp_path, monkeypatch, **argv_kwargs) -> str:
        output_file = _setup_output(tmp_path, monkeypatch)
        report_dir = tmp_path / "ai-review-results"
        with patch(
            "generate_quality_report.initialize_ai_review",
            return_value=str(report_dir),
        ):
            report_dir.mkdir(parents=True, exist_ok=True)
            rc = main(_make_argv(**argv_kwargs))
        assert rc == 0
        outputs = _read_outputs(output_file)
        return Path(outputs["report_file"]).read_text(encoding="utf-8")

    def test_caution_block_when_security_infrastructure(self, tmp_path, monkeypatch):
        content = self._render(
            tmp_path,
            monkeypatch,
            final_verdict="WARN",
            verdicts={"security": "NEEDS_REVIEW"},
            categories={"security": "INFRASTRUCTURE"},
        )
        assert "[!CAUTION]" in content
        assert "Security review did not run." in content
        assert "#4777" in content

    def test_no_caution_block_when_security_ran(self, tmp_path, monkeypatch):
        content = self._render(tmp_path, monkeypatch)
        assert "Security review did not run." not in content

    def test_no_caution_block_for_nonsecurity_infrastructure(
        self, tmp_path, monkeypatch
    ):
        content = self._render(
            tmp_path,
            monkeypatch,
            final_verdict="WARN",
            verdicts={"qa": "NEEDS_REVIEW"},
            categories={"qa": "INFRASTRUCTURE"},
        )
        assert "Security review did not run." not in content

    def test_caution_block_for_invalid_security_verdict(
        self, tmp_path, monkeypatch
    ):
        content = self._render(
            tmp_path,
            monkeypatch,
            final_verdict="UNKNOWN",
            verdicts={"security": "FOOBAR"},
            categories={"security": "CODE_QUALITY"},
        )
        assert "Security review did not run." in content
        assert "did not produce a valid result" in content


class TestSecurityReviewRan:
    def test_pass_without_infrastructure_ran(self):
        assert _security_review_ran("PASS", "N/A") is True

    def test_pass_with_infrastructure_did_not_run(self):
        assert _security_review_ran("PASS", "INFRASTRUCTURE") is False

    def test_did_not_run_without_category_did_not_run(self):
        assert _security_review_ran("DID_NOT_RUN", "CODE_QUALITY") is False

    def test_unknown_did_not_run(self):
        assert _security_review_ran("UNKNOWN", "CODE_QUALITY") is False


class TestBuildFindingsSections:
    def test_infra_empty_file_shows_did_not_run(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        findings_dir = Path("ai-review-results")
        findings_dir.mkdir(parents=True, exist_ok=True)
        (findings_dir / "security-findings.txt").write_text("")
        categories = {a: "N/A" for a in _AGENTS}
        categories["security"] = "INFRASTRUCTURE"
        result = _build_findings_sections(categories, security_review_ran=False)
        assert "did not run: no valid security review result" in result
        assert "Copilot CLI unavailable" not in result
        assert "No findings available (empty file)" not in result

    def test_non_infra_empty_file_shows_no_findings(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        findings_dir = Path("ai-review-results")
        findings_dir.mkdir(parents=True, exist_ok=True)
        (findings_dir / "security-findings.txt").write_text("")
        categories = {a: "N/A" for a in _AGENTS}
        result = _build_findings_sections(categories, security_review_ran=True)
        assert "No findings available (empty file)" in result
        assert "did not run" not in result

    def test_missing_file_shows_not_found(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        Path("ai-review-results").mkdir(parents=True, exist_ok=True)
        categories = {a: "N/A" for a in _AGENTS}
        result = _build_findings_sections(categories, security_review_ran=True)
        assert "Findings file not found" in result
