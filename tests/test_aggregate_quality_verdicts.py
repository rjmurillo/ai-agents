"""Tests for aggregate_quality_verdicts.py consumer script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

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


_mod = _import_script("aggregate_quality_verdicts")
main = _mod.main
build_parser = _mod.build_parser
get_category = _mod.get_category

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AGENTS = ("security", "qa", "analyst", "architect", "devops", "roadmap")


def _make_argv(verdicts: dict[str, str], infra: dict[str, str] | None = None) -> list[str]:
    """Build argv list from verdict/infra dicts."""
    argv: list[str] = []
    for agent in _AGENTS:
        argv.extend([f"--{agent}-verdict", verdicts.get(agent, "")])
        flag = (infra or {}).get(agent, "")
        argv.extend([f"--{agent}-infra", flag])
    return argv


def _capture_outputs(tmp_path: Path, monkeypatch):
    """Set GITHUB_OUTPUT and return a helper to read the outputs."""
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
# Tests: get_category
# ---------------------------------------------------------------------------


class TestGetCategory:
    def test_fail_verdict_with_infra_flag(self):
        assert get_category("CRITICAL_FAIL", True) == "INFRASTRUCTURE"

    def test_fail_verdict_without_infra_flag(self):
        assert get_category("CRITICAL_FAIL", False) == "CODE_QUALITY"

    def test_pass_verdict_returns_na(self):
        assert get_category("PASS", False) == "N/A"

    def test_pass_verdict_with_infra_returns_na(self):
        assert get_category("PASS", True) == "N/A"

    def test_warn_verdict_returns_na(self):
        assert get_category("WARN", False) == "N/A"

    @pytest.mark.parametrize("verdict", ["REJECTED", "FAIL", "NEEDS_REVIEW"])
    def test_all_fail_verdicts_classified(self, verdict):
        assert get_category(verdict, False) == "CODE_QUALITY"
        assert get_category(verdict, True) == "INFRASTRUCTURE"


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_parses_all_agents(self):
        argv = _make_argv(
            {"security": "PASS", "qa": "WARN"},
            {"security": "false", "qa": "true"},
        )
        args = build_parser().parse_args(argv)
        assert args.security_verdict == "PASS"
        assert args.qa_verdict == "WARN"
        assert args.qa_infra == "true"

    def test_defaults_to_empty(self, monkeypatch):
        for agent in _AGENTS:
            monkeypatch.delenv(f"{agent.upper()}_VERDICT", raising=False)
            monkeypatch.delenv(f"{agent.upper()}_INFRA", raising=False)
        args = build_parser().parse_args([])
        assert args.security_verdict == ""


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_all_pass_returns_0(self, tmp_path, monkeypatch):
        output_file = _capture_outputs(tmp_path, monkeypatch)
        verdicts = {a: "PASS" for a in _AGENTS}
        rc = main(_make_argv(verdicts))
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "PASS"

    def test_no_verdicts_returns_1(self, tmp_path, monkeypatch):
        output_file = _capture_outputs(tmp_path, monkeypatch)
        verdicts = {a: "" for a in _AGENTS}
        rc = main(_make_argv(verdicts))
        assert rc == 1
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"

    def test_code_quality_failure_not_downgraded(self, tmp_path, monkeypatch):
        output_file = _capture_outputs(tmp_path, monkeypatch)
        verdicts = {a: "PASS" for a in _AGENTS}
        verdicts["security"] = "CRITICAL_FAIL"
        infra = {a: "false" for a in _AGENTS}
        rc = main(_make_argv(verdicts, infra))
        assert rc == 0
        outputs = _read_outputs(output_file)
        # Should NOT be downgraded because it is CODE_QUALITY, not INFRASTRUCTURE
        assert outputs["final_verdict"] != "WARN"

    def test_all_infra_failures_downgraded_to_warn(self, tmp_path, monkeypatch):
        output_file = _capture_outputs(tmp_path, monkeypatch)
        verdicts = {a: "PASS" for a in _AGENTS}
        verdicts["security"] = "CRITICAL_FAIL"
        infra = {a: "false" for a in _AGENTS}
        infra["security"] = "true"
        rc = main(_make_argv(verdicts, infra))
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "WARN"

    def test_outputs_per_agent_verdicts_and_categories(self, tmp_path, monkeypatch):
        output_file = _capture_outputs(tmp_path, monkeypatch)
        verdicts = {a: "PASS" for a in _AGENTS}
        verdicts["qa"] = "FAIL"
        infra = {a: "false" for a in _AGENTS}
        rc = main(_make_argv(verdicts, infra))
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["qa_verdict"] == "FAIL"
        assert outputs["qa_category"] == "CODE_QUALITY"
        assert outputs["security_category"] == "N/A"

    def test_mixed_infra_and_code_failures(self, tmp_path, monkeypatch):
        output_file = _capture_outputs(tmp_path, monkeypatch)
        verdicts = {a: "PASS" for a in _AGENTS}
        verdicts["security"] = "FAIL"
        verdicts["qa"] = "FAIL"
        infra = {a: "false" for a in _AGENTS}
        infra["security"] = "true"
        # qa is CODE_QUALITY, security is INFRASTRUCTURE
        rc = main(_make_argv(verdicts, infra))
        assert rc == 0
        outputs = _read_outputs(output_file)
        # Not all failures are infra, so no downgrade
        assert outputs["final_verdict"] != "WARN"
