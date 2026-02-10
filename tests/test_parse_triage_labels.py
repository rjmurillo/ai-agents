"""Tests for parse_triage_labels.py consumer script."""

from __future__ import annotations

import importlib.util
import json
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


_mod = _import_script("parse_triage_labels")
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
        monkeypatch.delenv("FALLBACK_LABELS", raising=False)
        args = build_parser().parse_args([])
        assert args.raw_output == ""
        assert args.fallback_labels == ""

    def test_cli_args(self):
        args = build_parser().parse_args([
            "--raw-output", "test",
            "--fallback-labels", "bug,enhancement",
        ])
        assert args.raw_output == "test"
        assert args.fallback_labels == "bug,enhancement"


# ---------------------------------------------------------------------------
# Tests: main - label parsing
# ---------------------------------------------------------------------------


class TestMainLabels:
    def test_extracts_labels_from_ai_output(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = json.dumps({"labels": ["bug", "enhancement"]})
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        labels = json.loads(outputs["labels"])
        assert "bug" in labels
        assert "enhancement" in labels

    def test_fallback_labels_used_when_no_ai_labels(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        rc = main(["--raw-output", "", "--fallback-labels", "bug,docs"])
        assert rc == 0
        outputs = _read_outputs(output_file)
        labels = json.loads(outputs["labels"])
        assert "bug" in labels
        assert "docs" in labels

    def test_empty_output_empty_fallback(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        rc = main(["--raw-output", "", "--fallback-labels", ""])
        assert rc == 0
        outputs = _read_outputs(output_file)
        labels = json.loads(outputs["labels"])
        assert labels == []

    def test_unsafe_fallback_labels_rejected(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        rc = main([
            "--raw-output", "",
            "--fallback-labels", "good-label,$(evil),normal",
        ])
        assert rc == 0
        outputs = _read_outputs(output_file)
        labels = json.loads(outputs["labels"])
        assert "good-label" in labels
        assert "normal" in labels
        assert "$(evil)" not in labels


# ---------------------------------------------------------------------------
# Tests: main - category parsing
# ---------------------------------------------------------------------------


class TestMainCategory:
    def test_extracts_category(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        raw = '{"category": "bug-fix", "labels": ["bug"]}'
        rc = main(["--raw-output", raw])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["category"] == "bug-fix"

    def test_defaults_to_unknown(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        rc = main(["--raw-output", "no category here"])
        assert rc == 0
        outputs = _read_outputs(output_file)
        assert outputs["category"] == "unknown"

    def test_always_returns_0(self, tmp_path, monkeypatch):
        _setup_output(tmp_path, monkeypatch)
        rc = main(["--raw-output", "garbage data"])
        assert rc == 0
