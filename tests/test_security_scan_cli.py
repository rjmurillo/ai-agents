"""Focused CLI-surface tests for `scan_vulnerabilities.py`.

Scope: regression tests for the behavior changes introduced when CWE-22
detection was delegated to CodeQL (issue #1843, PR #1851). NOT a full pytest
suite for the scanner; the broader coverage gap is tracked at issue #1849.

Covered behaviors:

1. CWE-78 detection still works after CWE-22 removal.
2. `--cwe 22` emits a stderr WARNING and produces zero findings (delegated).
3. `--cwe N` for any unsupported N (e.g., 87) exits with EXIT_ERROR (1).
4. `summary.delegated_cwes` is present in JSON output with the expected
   `{tool, query, workflow}` shape for CWE-22.
5. JSON envelope carries `schema_version` (v2 contract).
6. Path-validation hardening: `--directory`, `--output`, and positional file
   args outside the scanner's cwd are rejected via `Path.resolve()` +
   `Path.is_relative_to()`.

Test isolation: every fixture writes under pytest's `tmp_path`. The scanner
is invoked with `cwd=tmp_path` so its `allowed_base` resolves to the same
directory. Paths under `tmp_path` are accepted; paths outside it (including
`tmp_path.parent`) are escape attempts. This keeps the repo working tree
clean and makes the tests portable across platforms (no hardcoded `/tmp` or
`/etc/passwd` paths).
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
    """Invoke the scanner with the project venv interpreter.

    Default `cwd=REPO_ROOT` is preserved for tests that do not need
    isolation; tests that exercise the path-validation contract pass an
    explicit `cwd` (typically `tmp_path`) so the scanner's `allowed_base`
    matches the test's containment boundary.
    """
    return subprocess.run(
        [sys.executable, str(SCANNER), *args],
        capture_output=True,
        text=True,
        cwd=cwd or REPO_ROOT,
        check=False,
    )


@pytest.fixture
def cwe78_fixture(tmp_path: Path) -> tuple[Path, str]:
    """Write a Python file containing one CWE-78 candidate inside tmp_path.

    Returns (cwd, filename). Tests pass `cwd` to `_scanner` so the scanner's
    `allowed_base` matches the fixture's directory.
    """
    target = tmp_path / "cwe78_smoke.py"
    target.write_text(
        "import subprocess\n"
        "def run(cmd):\n"
        "    subprocess.run(cmd, shell=True)\n",
        encoding="utf-8",
    )
    return tmp_path, target.name


@pytest.fixture
def clean_python_fixture(tmp_path: Path) -> tuple[Path, str]:
    """A Python file with no detector matches, written under tmp_path."""
    target = tmp_path / "clean_smoke.py"
    target.write_text("def hello() -> str:\n    return 'world'\n", encoding="utf-8")
    return tmp_path, target.name


def test_cwe78_detected_after_cwe22_delegation(cwe78_fixture: tuple[Path, str]) -> None:
    """Removing the CWE-22 dispatch must not affect CWE-78 detection."""
    cwd, name = cwe78_fixture
    result = _scanner(name, cwd=cwd)
    assert result.returncode == 10, f"Expected vulnerabilities exit code 10, got {result.returncode}"
    assert "CWE-78" in result.stdout
    assert "Command Injection" in result.stdout


def test_cwe22_flag_emits_warning_and_zero_findings(
    clean_python_fixture: tuple[Path, str],
) -> None:
    """`--cwe 22` must warn on stderr and report zero findings.

    Pins the literal `WARNING:` prefix so a refactor that renames the marker
    (e.g., to `NOTICE:` or `INFO:`) is caught; substring-only checks would
    pass silently.
    """
    cwd, name = clean_python_fixture
    result = _scanner("--cwe", "22", name, cwd=cwd)
    assert result.returncode == 0, f"Expected clean exit 0, got {result.returncode}"
    assert result.stderr.startswith("WARNING: --cwe 22"), (
        f"stderr must start with literal `WARNING: --cwe 22` so callers can "
        f"reliably grep for it; got: {result.stderr[:80]!r}"
    )
    assert "delegated to CodeQL" in result.stderr
    assert "python-security-extended.qls" in result.stderr


def test_cwe22_flag_does_not_pollute_stdout_or_json(
    clean_python_fixture: tuple[Path, str],
) -> None:
    """The deprecation warning belongs on stderr; stdout JSON stays clean."""
    cwd, name = clean_python_fixture
    result = _scanner("--cwe", "22", "--format", "json", name, cwd=cwd)
    assert result.returncode == 0
    assert "WARNING" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["vulnerabilities"] == []


def test_unsupported_cwe_value_rejected(clean_python_fixture: tuple[Path, str]) -> None:
    """`--cwe 87` (typo) must exit with EXIT_ERROR, not silently scan nothing."""
    cwd, name = clean_python_fixture
    result = _scanner("--cwe", "87", name, cwd=cwd)
    assert result.returncode == 1, f"Expected EXIT_ERROR, got {result.returncode}"
    assert "ERROR: --cwe" in result.stderr
    assert "not supported" in result.stderr


def test_cwe78_value_accepted(cwe78_fixture: tuple[Path, str]) -> None:
    """Sanity: `--cwe 78` is the supported value and still works."""
    cwd, name = cwe78_fixture
    result = _scanner("--cwe", "78", name, cwd=cwd)
    assert result.returncode == 10
    assert "CWE-78" in result.stdout


def test_json_summary_has_delegated_cwes_field(
    clean_python_fixture: tuple[Path, str],
) -> None:
    """`summary.delegated_cwes` must be present and shaped correctly,
    and the envelope must carry `schema_version` per ADR-054 amendment."""
    cwd, name = clean_python_fixture
    result = _scanner("--format", "json", name, cwd=cwd)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 2, (
        "JSON envelope must carry schema_version=2 so consumers can detect "
        "schema evolution"
    )
    delegated = payload["summary"]["delegated_cwes"]
    assert "CWE-22" in delegated
    entry = delegated["CWE-22"]
    assert isinstance(entry, dict), "delegated_cwes entry must be a dict, not a string"
    assert entry["tool"] == "codeql"
    assert entry["query"] == "python-security-extended.qls"
    assert entry["workflow"] == ".github/workflows/codeql-analysis.yml"


def test_json_delegated_cwes_present_when_findings_exist(
    cwe78_fixture: tuple[Path, str],
) -> None:
    """`summary.delegated_cwes` must remain in the JSON envelope even when
    real CWE-78 findings are present. Regression for the case where a
    refactor of the findings-present codepath could silently drop the field."""
    cwd, name = cwe78_fixture
    result = _scanner("--format", "json", name, cwd=cwd)
    assert result.returncode == 10, "expected vulnerabilities exit code"
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 2
    assert "delegated_cwes" in payload["summary"]
    assert "CWE-22" in payload["summary"]["delegated_cwes"]
    assert len(payload["vulnerabilities"]) >= 1, "CWE-78 must be detected"


def test_directory_outside_cwd_rejected(tmp_path: Path) -> None:
    """The hardened path validation must reject directory paths escaping
    the scanner's cwd. `tmp_path.parent` is, by construction, outside
    `tmp_path` (pytest creates `tmp_path` as a fresh sub-directory)."""
    escape = tmp_path.parent
    result = _scanner("--directory", str(escape), cwd=tmp_path)
    assert result.returncode == 1
    assert "Path traversal attempt detected in --directory" in result.stderr


def test_output_outside_cwd_rejected(
    clean_python_fixture: tuple[Path, str], tmp_path: Path,
) -> None:
    """The same path validation must apply to `--output`. Regression for the
    QA gap noted on PR #1851: `--output` had zero test coverage."""
    cwd, name = clean_python_fixture
    escape_target = tmp_path.parent / "scan_out.json"
    result = _scanner("--output", str(escape_target), name, cwd=cwd)
    assert result.returncode == 1
    assert "Path traversal attempt detected in --output" in result.stderr


def test_positional_file_outside_cwd_rejected(tmp_path: Path) -> None:
    """The `_validate_path` closure also runs on positional file args.
    Regression for the QA-flagged gap: only `--directory` and `--output`
    had explicit tests; a positional path escape would have gone undetected
    if the closure regressed."""
    escape_target = tmp_path.parent / "outside_target.py"
    result = _scanner(str(escape_target), cwd=tmp_path)
    assert result.returncode == 1
    assert "Path traversal attempt detected in file" in result.stderr


def test_cwe_mixed_78_and_22_emits_warning_runs_cwe78(
    cwe78_fixture: tuple[Path, str],
) -> None:
    """`--cwe 78 --cwe 22` (action=append) must run the CWE-78 scan AND emit
    the CWE-22 delegation warning. The set-difference logic
    (`set(args.cwe) - {78} - {22}`) yields empty, so no error; the
    `if 22 in args.cwe` branch fires the warning."""
    cwd, name = cwe78_fixture
    result = _scanner("--cwe", "78", "--cwe", "22", name, cwd=cwd)
    assert result.returncode == 10, "CWE-78 finding must still be detected"
    assert "CWE-78" in result.stdout
    assert result.stderr.startswith("WARNING: --cwe 22"), (
        "CWE-22 delegation warning must still fire when 22 is in the list"
    )


def test_console_output_includes_cwe22_delegation_when_requested(
    clean_python_fixture: tuple[Path, str],
) -> None:
    """Console output (not just JSON) must surface CWE-22 delegation when
    `--cwe 22` is requested. JSON callers see `summary.delegated_cwes`;
    console callers must see an equivalent stdout marker."""
    cwd, name = clean_python_fixture
    result = _scanner("--cwe", "22", name, cwd=cwd)
    assert result.returncode == 0
    assert "CWE-22: delegated to CodeQL" in result.stdout, (
        "console output must mention CWE-22 delegation when --cwe 22 is "
        "requested; JSON-only signaling is insufficient for console callers"
    )


def test_path_validation_uses_resolve_not_startswith(tmp_path: Path) -> None:
    """Regression: prefix-string `startswith` would let `/foo/barevil` pass a
    `/foo/bar` check. The `Path.is_relative_to()` implementation rejects it.

    We construct a sibling directory whose path-string starts with `tmp_path`
    but is not actually inside it. `is_relative_to` is path-component aware
    and rejects the escape; the prior `os.path.abspath + str.startswith`
    implementation would have accepted it (false negative).
    """
    sibling_with_matching_prefix = tmp_path.parent / (tmp_path.name + "extra")
    result = _scanner("--directory", str(sibling_with_matching_prefix), cwd=tmp_path)
    assert result.returncode == 1
    assert "Path traversal attempt detected" in result.stderr
