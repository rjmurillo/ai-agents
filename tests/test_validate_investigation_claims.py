"""Tests for validate_investigation_claims.py CI backstop script."""

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


_mod = _import_script("validate_investigation_claims")
main = _mod.main
validate_claims = _mod.validate_claims
get_changed_files = _mod.get_changed_files
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
    def test_defaults(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.base_ref == "HEAD~1"
        assert args.head_ref == "HEAD"

    def test_custom_refs(self):
        parser = build_parser()
        args = parser.parse_args(["--base-ref", "abc123", "--head-ref", "def456"])
        assert args.base_ref == "abc123"
        assert args.head_ref == "def456"


# ---------------------------------------------------------------------------
# Tests: validate_claims (pure logic, no git)
# ---------------------------------------------------------------------------


class TestValidateClaims:
    def test_all_allowed_files(self):
        files = [
            ".agents/sessions/2026-01-01-session-01.json",
            ".agents/analysis/report.md",
            ".agents/retrospective/retro.md",
            ".serena/memories/test.md",
            ".agents/security/scan.md",
            ".agents/critique/review.md",
        ]
        assert validate_claims(files) == []

    def test_violation_detected(self):
        files = [
            ".agents/sessions/2026-01-01-session-01.json",
            "src/main.py",
        ]
        violations = validate_claims(files)
        assert violations == ["src/main.py"]

    def test_multiple_violations(self):
        files = [
            "README.md",
            ".github/workflows/test.yml",
            ".agents/sessions/log.json",
        ]
        violations = validate_claims(files)
        assert len(violations) == 2
        assert "README.md" in violations
        assert ".github/workflows/test.yml" in violations

    def test_empty_file_list(self):
        assert validate_claims([]) == []


# ---------------------------------------------------------------------------
# Tests: main (integration)
# ---------------------------------------------------------------------------


class TestMain:
    def test_no_changed_files(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        with patch.object(_mod, "get_changed_files", return_value=[]):
            exit_code = main([])
        assert exit_code == 0
        outputs = _read_outputs(output_file)
        assert outputs["investigation_violations"] == "0"

    def test_all_compliant(self, tmp_path, monkeypatch):
        output_file = _setup_output(tmp_path, monkeypatch)
        compliant_files = [
            ".agents/sessions/2026-01-01-session-01.json",
            ".agents/analysis/report.md",
        ]
        with patch.object(_mod, "get_changed_files", return_value=compliant_files):
            exit_code = main([])
        assert exit_code == 0
        outputs = _read_outputs(output_file)
        assert outputs["investigation_violations"] == "0"

    def test_violations_still_exits_zero(self, tmp_path, monkeypatch):
        """Advisory mode: violations produce exit 0."""
        output_file = _setup_output(tmp_path, monkeypatch)
        mixed_files = [
            ".agents/sessions/2026-01-01-session-01.json",
            "src/main.py",
            "README.md",
        ]
        with patch.object(_mod, "get_changed_files", return_value=mixed_files):
            exit_code = main([])
        assert exit_code == 0
        outputs = _read_outputs(output_file)
        assert outputs["investigation_violations"] == "2"
