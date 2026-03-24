"""Tests for parse_feature_review.py consumer script."""

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
    assert spec is not None, f"Could not load spec for {name}"
    assert spec.loader is not None, f"Spec for {name} has no loader"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("parse_feature_review")
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
        args = build_parser().parse_args([])
        assert args.raw_output == ""

    def test_cli_args(self):
        args = build_parser().parse_args(["--raw-output", "test content"])
        assert args.raw_output == "test content"


# ---------------------------------------------------------------------------
# Tests: main - recommendation parsing
# ---------------------------------------------------------------------------


class TestMainRecommendation:
    def test_extracts_proceed_recommendation(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = "RECOMMENDATION: PROCEED\nRationale: looks good"
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["recommendation"] == "PROCEED"

    def test_extracts_decline_recommendation(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = "RECOMMENDATION: DECLINE\nRationale: out of scope"
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["recommendation"] == "DECLINE"

    def test_returns_unknown_for_empty_input(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        rc = main(["--raw-output", ""])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["recommendation"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# Tests: main - assignees parsing
# ---------------------------------------------------------------------------


class TestMainAssignees:
    def test_extracts_assignees(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = "**Assignees**: @user1, @user2"
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["assignees"] == "user1,user2"

    def test_returns_empty_for_none_suggested(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = "**Assignees**: none suggested"
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["assignees"] == ""


# ---------------------------------------------------------------------------
# Tests: main - labels parsing
# ---------------------------------------------------------------------------


class TestMainLabels:
    def test_extracts_backtick_labels(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = "**Labels**: `bug`, `enhancement`"
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["labels"] == "bug,enhancement"

    def test_returns_empty_for_none(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = "**Labels**: none"
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["labels"] == ""


# ---------------------------------------------------------------------------
# Tests: main - full integration
# ---------------------------------------------------------------------------


class TestMainIntegration:
    def test_parses_full_output(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = """## Recommendation

RECOMMENDATION: DEFER

**Rationale**: Needs more research.

## Suggested Actions

- **Assignees**: @rjmurillo
- **Labels**: `needs-research`, `enhancement`
- **Milestone**: backlog
"""
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["recommendation"] == "DEFER"
        assert outputs["assignees"] == "rjmurillo"
        assert "needs-research" in outputs["labels"]

    def test_always_returns_0(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        rc = main(["--raw-output", "garbage data with no structure"])
        assert rc == 0
