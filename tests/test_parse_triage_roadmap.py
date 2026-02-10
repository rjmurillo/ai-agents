"""Tests for parse_triage_roadmap.py consumer script."""

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
    assert spec is not None, f"Could not load spec for {name}"
    assert spec.loader is not None, f"Spec for {name} has no loader"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("parse_triage_roadmap")
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


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_defaults_to_empty(self, monkeypatch):
        monkeypatch.delenv("RAW_OUTPUT", raising=False)
        monkeypatch.delenv("MILESTONE_FROM_ACTION", raising=False)
        args = build_parser().parse_args([])
        assert args.raw_output == ""
        assert args.milestone_from_action == ""

    def test_cli_args(self):
        args = build_parser().parse_args([
            "--raw-output", "test",
            "--milestone-from-action", "v1.0.0",
        ])
        assert args.raw_output == "test"
        assert args.milestone_from_action == "v1.0.0"


# ---------------------------------------------------------------------------
# Tests: main - milestone parsing
# ---------------------------------------------------------------------------


class TestMainMilestone:
    def test_extracts_milestone_from_ai_output(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = '{"milestone": "v0.3.0"}'
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["milestone"] == "v0.3.0"

    def test_fallback_milestone_used(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        rc = main(["--raw-output", "", "--milestone-from-action", "v1.0.0"])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["milestone"] == "v1.0.0"

    def test_unsafe_fallback_milestone_rejected(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        rc = main([
            "--raw-output", "",
            "--milestone-from-action", "$(evil)",
        ])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["milestone"] == ""

    def test_empty_milestone(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        rc = main(["--raw-output", "no milestone here"])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["milestone"] == ""


# ---------------------------------------------------------------------------
# Tests: main - priority parsing
# ---------------------------------------------------------------------------


class TestMainPriority:
    def test_extracts_priority(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = '{"priority": "P0"}'
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["priority"] == "P0"

    def test_defaults_to_p2(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        rc = main(["--raw-output", ""])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["priority"] == "P2"

    @pytest.mark.parametrize("priority", ["P0", "P1", "P2", "P3", "P4"])
    def test_all_valid_priorities(self, priority, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = f'{{"priority": "{priority}"}}'
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["priority"] == priority


# ---------------------------------------------------------------------------
# Tests: main - escalation parsing
# ---------------------------------------------------------------------------


class TestMainEscalation:
    def test_extracts_escalate_to_prd(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = '{"escalate_to_prd": true}'
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["escalate_to_prd"] == "true"

    def test_defaults_to_false(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        rc = main(["--raw-output", ""])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["escalate_to_prd"] == "false"


# ---------------------------------------------------------------------------
# Tests: main - complexity score
# ---------------------------------------------------------------------------


class TestMainComplexity:
    def test_extracts_complexity_score(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = '{"complexity_score": 7}'
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["complexity_score"] == "7"

    def test_caps_at_12(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = '{"complexity_score": 99}'
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["complexity_score"] == "12"

    def test_defaults_to_0(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        rc = main(["--raw-output", ""])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["complexity_score"] == "0"


# ---------------------------------------------------------------------------
# Tests: main - escalation criteria
# ---------------------------------------------------------------------------


class TestMainEscalationCriteria:
    def test_extracts_criteria(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = '{"escalation_criteria": ["scope-change", "risk-high"]}'
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert "scope-change" in outputs["escalation_criteria"]
        assert "risk-high" in outputs["escalation_criteria"]

    def test_unsafe_criteria_rejected(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = '{"escalation_criteria": ["good-item", "$(evil)", "ok-item"]}'
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert "good-item" in outputs["escalation_criteria"]
        assert "ok-item" in outputs["escalation_criteria"]
        assert "$(evil)" not in outputs["escalation_criteria"]

    def test_empty_criteria(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        rc = main(["--raw-output", ""])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["escalation_criteria"] == ""

    def test_always_returns_0(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        rc = main(["--raw-output", "garbage"])
        assert rc == 0
