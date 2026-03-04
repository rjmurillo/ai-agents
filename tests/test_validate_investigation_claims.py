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
    """Parse GitHub Actions output file supporting both formats.

    Heredoc format: ``key<<delimiter`` (no ``=`` before ``<<``)
    Simple format: ``key=value`` (may contain ``<<`` in value)

    Example heredoc::

        key<<delimiter
        multiline value
        delimiter
    """
    text = output_file.read_text()
    lines = text.splitlines()
    result: dict[str, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        # Heredoc: key<<delimiter (no = before <<)
        eq_pos = line.find("=")
        heredoc_pos = line.find("<<")
        if heredoc_pos != -1 and (eq_pos == -1 or heredoc_pos < eq_pos):
            key, delimiter = line.split("<<", 1)
            value_lines: list[str] = []
            i += 1
            while i < len(lines) and lines[i] != delimiter:
                value_lines.append(lines[i])
                i += 1
            result[key] = "\n".join(value_lines)
            i += 1  # skip closing delimiter
        elif eq_pos != -1:
            k, v = line.split("=", 1)
            result[k] = v
            i += 1
        else:
            i += 1
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

    def test_multiline_violation_details_use_heredoc(self, tmp_path, monkeypatch):
        """Multiline violation_details must use heredoc format (#1386)."""
        output_file = _setup_output(tmp_path, monkeypatch)
        mixed_files = [
            ".agents/sessions/2026-01-01-session-01.json",
            "src/main.py",
            "README.md",
        ]
        with patch.object(_mod, "get_changed_files", return_value=mixed_files):
            exit_code = main([])
        assert exit_code == 0

        raw = output_file.read_text()
        # The multiline value must NOT appear as bare key=value lines
        assert "violation_details=  - " not in raw
        # It must use heredoc delimiter format (key<<delimiter)
        assert any(line.startswith("violation_details<<") for line in raw.splitlines())

        outputs = _read_outputs(output_file)
        assert "src/main.py" in outputs["violation_details"]
        assert "README.md" in outputs["violation_details"]

    def test_base_ref_injection_rejected(self, tmp_path, monkeypatch, capsys):
        """Refs starting with a dash are rejected (CWE-78)."""
        _setup_output(tmp_path, monkeypatch)
        exit_code = main(["--base-ref=--staged"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "cannot start with a dash" in captured.err.lower()

    def test_head_ref_injection_rejected(self, tmp_path, monkeypatch, capsys):
        """Refs starting with a dash are rejected (CWE-78)."""
        _setup_output(tmp_path, monkeypatch)
        exit_code = main(["--head-ref=--quiet"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "cannot start with a dash" in captured.err.lower()
