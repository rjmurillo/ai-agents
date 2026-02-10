"""Tests for aggregate_session_verdicts.py consumer script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

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


_mod = _import_script("aggregate_session_verdicts")
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


def _create_verdict_file(results_dir: Path, name: str, verdict: str) -> None:
    (results_dir / f"{name}-verdict.txt").write_text(verdict)


def _create_must_file(results_dir: Path, name: str, content: str) -> None:
    (results_dir / f"{name}-must-failures.txt").write_text(content)


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_default_results_dir(self):
        args = build_parser().parse_args([])
        assert args.results_dir == "validation-results"

    def test_custom_results_dir(self):
        args = build_parser().parse_args(["--results-dir", "/custom/path"])
        assert args.results_dir == "/custom/path"


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_no_verdict_files_returns_warn(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        rc = main(["--results-dir", str(results_dir)])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "WARN"

    def test_all_pass_returns_pass(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "PASS")
        _create_verdict_file(results_dir, "session-2", "PASS")
        rc = main(["--results-dir", str(results_dir)])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "PASS"

    def test_critical_fail_verdict_propagates(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "PASS")
        _create_verdict_file(results_dir, "session-2", "CRITICAL_FAIL")
        rc = main(["--results-dir", str(results_dir)])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"

    def test_rejected_verdict_propagates(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "REJECTED")
        rc = main(["--results-dir", str(results_dir)])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"

    def test_warn_verdict_upgrades_pass_to_warn(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "PASS")
        _create_verdict_file(results_dir, "session-2", "WARN")
        rc = main(["--results-dir", str(results_dir)])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "WARN"

    def test_must_failures_override_to_critical_fail(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "PASS")
        _create_must_file(results_dir, "session-1", "3")
        rc = main(["--results-dir", str(results_dir)])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"
        assert outputs["must_failures"] == "3"

    def test_zero_must_failures_no_override(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "PASS")
        _create_must_file(results_dir, "session-1", "0")
        rc = main(["--results-dir", str(results_dir)])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "PASS"

    def test_must_failures_with_text_prefix(self, tmp_path, monkeypatch):
        """Non-numeric must-failures content starts with a digit."""
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "PASS")
        _create_must_file(results_dir, "session-1", "2 failures found")
        rc = main(["--results-dir", str(results_dir)])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"
        assert outputs["must_failures"] == "2"

    def test_non_compliant_verdict_is_critical_fail(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _create_verdict_file(results_dir, "session-1", "NON_COMPLIANT")
        rc = main(["--results-dir", str(results_dir)])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["final_verdict"] == "CRITICAL_FAIL"
