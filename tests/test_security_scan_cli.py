"""Focused CLI-surface tests for `scan_vulnerabilities.py`.

Scope: regression tests for the behavior changes introduced when CWE-22
detection was delegated to CodeQL (issue #1843). NOT a full pytest suite for
the scanner — the broader coverage gap is tracked at issue #1849.

Covered behaviors:
    1. CWE-78 detection still works after CWE-22 removal.
    2. `--cwe 22` emits a stderr WARNING and produces zero findings (delegated).
    3. `--cwe N` for any unsupported N (e.g., 87) exits with EXIT_ERROR (1).
    4. `summary.delegated_cwes` is present in JSON output with the expected
       `{tool, query, workflow}` shape for CWE-22.
    5. Path-validation hardening: `--directory` outside cwd is rejected via
       the new Path.resolve() + is_relative_to() check.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER = REPO_ROOT / ".claude" / "skills" / "security-scan" / "scripts" / "scan_vulnerabilities.py"


def _scanner(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Invoke the scanner with the project venv interpreter."""
    return subprocess.run(
        [sys.executable, str(SCANNER), *args],
        capture_output=True,
        text=True,
        cwd=cwd or REPO_ROOT,
        check=False,
    )


@pytest.fixture
def cwe78_fixture() -> Path:
    """Write a Python file with one CWE-78 candidate inside the repo tree
    (the scanner rejects paths outside cwd, which is the repo root)."""
    target = REPO_ROOT / "_test_cwe78_smoke.py"
    target.write_text(
        "import subprocess\n"
        "def run(cmd):\n"
        "    subprocess.run(cmd, shell=True)\n",
        encoding="utf-8",
    )
    yield target
    target.unlink(missing_ok=True)


@pytest.fixture
def clean_python_fixture() -> Path:
    """A Python file with no detector matches."""
    target = REPO_ROOT / "_test_clean_smoke.py"
    target.write_text("def hello() -> str:\n    return 'world'\n", encoding="utf-8")
    yield target
    target.unlink(missing_ok=True)


def test_cwe78_detected_after_cwe22_delegation(cwe78_fixture: Path) -> None:
    """Removing the CWE-22 dispatch must not affect CWE-78 detection."""
    result = _scanner(str(cwe78_fixture.relative_to(REPO_ROOT)))
    assert result.returncode == 10, f"Expected vulnerabilities exit code 10, got {result.returncode}"
    assert "CWE-78" in result.stdout
    assert "Command Injection" in result.stdout


def test_cwe22_flag_emits_warning_and_zero_findings(clean_python_fixture: Path) -> None:
    """`--cwe 22` must warn on stderr and report zero findings."""
    result = _scanner("--cwe", "22", str(clean_python_fixture.relative_to(REPO_ROOT)))
    assert result.returncode == 0, f"Expected clean exit 0, got {result.returncode}"
    assert "WARNING: --cwe 22" in result.stderr
    assert "delegated to CodeQL" in result.stderr
    assert "python-security-extended.qls" in result.stderr


def test_cwe22_flag_does_not_pollute_stdout_or_json(clean_python_fixture: Path) -> None:
    """The deprecation warning belongs on stderr; stdout JSON stays clean."""
    result = _scanner(
        "--cwe", "22", "--format", "json",
        str(clean_python_fixture.relative_to(REPO_ROOT)),
    )
    assert result.returncode == 0
    assert "WARNING" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["vulnerabilities"] == []


def test_unsupported_cwe_value_rejected(clean_python_fixture: Path) -> None:
    """`--cwe 87` (typo) must exit with EXIT_ERROR, not silently scan nothing."""
    result = _scanner("--cwe", "87", str(clean_python_fixture.relative_to(REPO_ROOT)))
    assert result.returncode == 1, f"Expected EXIT_ERROR, got {result.returncode}"
    assert "ERROR: --cwe" in result.stderr
    assert "not supported" in result.stderr


def test_cwe78_value_accepted(cwe78_fixture: Path) -> None:
    """Sanity: `--cwe 78` is the supported value and still works."""
    result = _scanner("--cwe", "78", str(cwe78_fixture.relative_to(REPO_ROOT)))
    assert result.returncode == 10
    assert "CWE-78" in result.stdout


def test_json_summary_has_delegated_cwes_field(clean_python_fixture: Path) -> None:
    """`summary.delegated_cwes` must be present and shaped correctly."""
    result = _scanner(
        "--format", "json",
        str(clean_python_fixture.relative_to(REPO_ROOT)),
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    delegated = payload["summary"]["delegated_cwes"]
    assert "CWE-22" in delegated
    entry = delegated["CWE-22"]
    assert isinstance(entry, dict), "delegated_cwes entry must be a dict, not a string"
    assert entry["tool"] == "codeql"
    assert entry["query"] == "python-security-extended.qls"
    assert entry["workflow"] == ".github/workflows/codeql-analysis.yml"


def test_directory_outside_cwd_rejected() -> None:
    """The hardened path validation must reject paths escaping the cwd."""
    result = _scanner("--directory", "/tmp")
    assert result.returncode == 1
    assert "Path traversal attempt detected" in result.stderr


def test_output_outside_cwd_rejected(clean_python_fixture: Path) -> None:
    """The same path validation must apply to --output. Regression for the
    QA gap noted on PR #1851: --output had zero test coverage."""
    result = _scanner(
        "--output", "/tmp/scan_out.json",
        str(clean_python_fixture.relative_to(REPO_ROOT)),
    )
    assert result.returncode == 1
    assert "Path traversal attempt detected in --output" in result.stderr


def test_path_validation_uses_resolve_not_startswith(tmp_path: Path) -> None:
    """Regression: prefix-string `startswith` would let `/foo/barevil` pass a
    `/foo/bar` check. The Path.is_relative_to() implementation rejects it.

    We construct a sibling directory whose prefix matches the cwd path and
    verify it is rejected. This is environment-sensitive (we need a sibling
    of cwd to exist), so we synthesize one in tmp_path and verify the scanner
    correctly rejects a relative escape via `..`.
    """
    # Path-component containment: ../<repo_basename>extra would have passed
    # the old startswith check but Path.is_relative_to() rejects it.
    repo_name = REPO_ROOT.name
    escape_attempt = f"../{repo_name}-doesnotexist"
    result = _scanner("--directory", escape_attempt)
    assert result.returncode == 1
    assert "Path traversal attempt detected" in result.stderr
