"""Detector-level coverage for `scan_vulnerabilities.py` (CWE-78 scanner).

Scope: the regex detector and its helpers, complementary to the focused CLI
regression suite in `tests/test_security_scan_cli.py`. That file pins the
CWE-22-delegation behavior, path validation, and JSON envelope. This file
covers the detector itself: every CWE-78 pattern across Python, PowerShell,
Bash, and C#; negative cases that must NOT fire; the per-line suppression
mechanism; and the language-detection and file-reading helpers. The broad
coverage gap was tracked at issue #1849.

These tests assert what the detector does today (characterization), not what
an idealized detector would do. Where the regex has a known weakness (it
flags commented-out code, and its "string concatenation" pattern only fires
on a `+` inside the quoted argument rather than on real concatenation), the
test documents the actual behavior in its name and docstring rather than
encoding an imagined contract. See `.claude/rules/canonical-source-mirror.md`
and `.claude/rules/working-with-legacy-code.md`.

The module under test lives outside the package tree, so it is loaded by path
via `importlib`. `conftest.py` already puts the repo root on `sys.path`; the
scanner script imports only stdlib, so a path-based load is safe and avoids a
dependency on the script being importable as a package.

CLI exit-code tests invoke the scanner as a subprocess (the only way to
observe `sys.exit` codes) with `cwd=tmp_path` so the scanner's path-traversal
`allowed_base` resolves to the same directory the fixtures are written under.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "security-scan"
    / "scripts"
    / "scan_vulnerabilities.py"
)


def _load_scanner() -> ModuleType:
    """Load the scanner module by path (it is not on the package tree)."""
    spec = importlib.util.spec_from_file_location(
        "scan_vulnerabilities", SCANNER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scanner = _load_scanner()


def test_path_based_import_removes_temporary_sibling_import_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Path-based import must not leave the scanner directory on sys.path."""
    script_dir = str(SCANNER_PATH.parent)
    monkeypatch.setattr(
        sys,
        "path",
        [entry for entry in sys.path if entry != script_dir],
    )
    for module_name in [
        "scan_constants",
        "scan_format",
        "scan_patterns",
        "scan_vulnerabilities_path_isolation",
    ]:
        monkeypatch.delitem(sys.modules, module_name, raising=False)

    spec = importlib.util.spec_from_file_location(
        "scan_vulnerabilities_path_isolation",
        SCANNER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "scan_vulnerabilities_path_isolation", module)
    spec.loader.exec_module(module)

    assert script_dir not in sys.path


def _descriptions_for(language: str, line: str) -> list[str]:
    """Return descriptions of every CWE-78 pattern that matches `line`.

    This bypasses `scan_file`'s per-line `break` so a single line can be
    checked against the whole pattern set for a language. Used by the
    parametrized positive and negative pattern tests.
    """
    descriptions = []
    for info in scanner.CWE78_PATTERNS[language]:
        pattern = cast(re.Pattern[str], info["pattern"])
        if pattern.search(line):
            descriptions.append(str(info["description"]))
    return descriptions


def _write(tmp_path: Path, name: str, body: str) -> str:
    """Write `body` to `tmp_path/name` and return the bare filename.

    Returning the filename (not the absolute path) lets callers invoke the
    scanner with `cwd=tmp_path` so its `allowed_base` containment check
    accepts the file.
    """
    (tmp_path / name).write_text(body, encoding="utf-8")
    return name


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("module.py", "python"),
        ("Deploy.ps1", "powershell"),
        ("Helpers.psm1", "powershell"),
        ("setup.sh", "bash"),
        ("run.bash", "bash"),
        ("Program.cs", "csharp"),
        ("UPPER.PY", "python"),
        ("notes.txt", None),
        ("Dockerfile", None),
        ("archive.tar.gz", None),
    ],
)
def test_get_language_maps_extension(filename: str, expected: str | None) -> None:
    assert scanner.get_language(str(Path(__file__).parent / filename)) == expected


def test_get_language_detects_extensionless_bash_shebang(tmp_path: Path) -> None:
    hook = tmp_path / "pre-push"
    hook.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$msg\"\n", encoding="utf-8")

    assert scanner.get_language(str(hook)) == "bash"


def test_get_language_ignores_extensionless_non_bash_shebang(tmp_path: Path) -> None:
    script = tmp_path / "utility"
    script.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")

    assert scanner.get_language(str(script)) is None


# ---------------------------------------------------------------------------
# CWE-78 positive detections, one parametrize per language
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "description", "severity"),
    [
        (
            'subprocess.run(f"ls {target}")',
            "Subprocess with f-string command (potential injection)",
            "CRITICAL",
        ),
        (
            "subprocess.call(cmd, shell=True)",
            "Subprocess with shell=True",
            "HIGH",
        ),
        (
            'subprocess.Popen(f"echo {x}")',
            "Subprocess with f-string command (potential injection)",
            "CRITICAL",
        ),
        (
            "eval(user_input)",
            "eval() with potentially unvalidated input",
            "CRITICAL",
        ),
        (
            "exec(command_blob)",
            "exec() with potentially unvalidated input",
            "CRITICAL",
        ),
    ],
)
def test_python_patterns_match(
    line: str, description: str, severity: str
) -> None:
    assert description in _descriptions_for("python", line)
    info = next(
        i
        for i in scanner.CWE78_PATTERNS["python"]
        if i["description"] == description
    )
    assert info["severity"] == severity


@pytest.mark.parametrize(
    ("line", "description", "severity"),
    [
        (
            'Invoke-Expression "run $thing"',
            "Invoke-Expression with variable interpolation",
            "CRITICAL",
        ),
        (
            "Invoke-Expression $userInput",
            "Invoke-Expression with potentially unvalidated input",
            "CRITICAL",
        ),
        (
            "& $commandPath",
            "Call operator with potentially unvalidated command",
            "HIGH",
        ),
        (
            "Start-Process notepad -ArgumentList $userArgs",
            "Start-Process with potentially unvalidated arguments",
            "HIGH",
        ),
    ],
)
def test_powershell_patterns_match(
    line: str, description: str, severity: str
) -> None:
    assert description in _descriptions_for("powershell", line)
    info = next(
        i
        for i in scanner.CWE78_PATTERNS["powershell"]
        if i["description"] == description
    )
    assert info["severity"] == severity


@pytest.mark.parametrize(
    ("line", "description", "severity"),
    [
        ('eval "$cmd"', "eval with variable expansion", "CRITICAL"),
        (
            "result=$( $userCommand )",
            "Command substitution with potentially unvalidated input",
            "CRITICAL",
        ),
        (
            "result=`$userInput`",
            "Backtick command substitution with potentially unvalidated input",
            "CRITICAL",
        ),
        (
            "echo $unquoted",
            "Unquoted variable expansion (potential word splitting/injection)",
            "MEDIUM",
        ),
    ],
)
def test_bash_patterns_match(line: str, description: str, severity: str) -> None:
    assert description in _descriptions_for("bash", line)
    info = next(
        i
        for i in scanner.CWE78_PATTERNS["bash"]
        if i["description"] == description
    )
    assert info["severity"] == severity


@pytest.mark.parametrize(
    ("line", "description", "severity"),
    [
        (
            "Process.Start(userCommand);",
            "Process.Start with potentially unvalidated command",
            "HIGH",
        ),
        (
            'var psi = new ProcessStartInfo { Arguments = $"-c {y}" };',
            "ProcessStartInfo with interpolated arguments",
            "HIGH",
        ),
        (
            "var p = new Process() { FileName = userCmd };",
            "Process with potentially unvalidated FileName",
            "HIGH",
        ),
    ],
)
def test_csharp_patterns_match(
    line: str, description: str, severity: str
) -> None:
    assert description in _descriptions_for("csharp", line)
    info = next(
        i
        for i in scanner.CWE78_PATTERNS["csharp"]
        if i["description"] == description
    )
    assert info["severity"] == severity


# ---------------------------------------------------------------------------
# Severity is carried through to the Vulnerability record
# ---------------------------------------------------------------------------


def test_scan_file_populates_vulnerability_fields(tmp_path: Path) -> None:
    name = _write(
        tmp_path,
        "iex.ps1",
        "Invoke-Expression $userInput\n",
    )
    vulns, suppressed = scanner.scan_file(str(tmp_path / name))
    assert suppressed == []
    assert len(vulns) == 1
    vuln = vulns[0]
    assert vuln.cwe == "CWE-78"
    assert vuln.title == "Command Injection Vulnerability"
    assert vuln.line == 1
    assert vuln.severity == "CRITICAL"
    assert vuln.code == "Invoke-Expression $userInput"
    assert "Invoke-Expression" in vuln.pattern


# ---------------------------------------------------------------------------
# Negative cases: safe constructs must NOT be flagged
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "line"),
    [
        ("python", 'subprocess.run(["ls", "-l"])'),
        ("python", "subprocess.run(args, shell=False)"),
        ("python", 'subprocess.run(["git", "status"], check=True)'),
        ("python", 'eval("1 + 1")'),
        ("python", "x = compute(value)"),
        ("powershell", 'Write-Output "done"'),
        ("powershell", "Get-ChildItem -Path $home"),
        ("bash", 'echo "$quoted"'),
        ("bash", 'printf "%s\\n" "$value"'),
        ("csharp", 'Console.WriteLine("hello");'),
        ("csharp", "var total = a + b;"),
    ],
)
def test_safe_lines_not_flagged(language: str, line: str) -> None:
    assert _descriptions_for(language, line) == []


def test_python_string_concat_pattern_requires_plus_inside_literal() -> None:
    """Characterization: the 'string concatenation' regex fires only on a `+`
    inside the opening quoted argument, NOT on real concatenation.

    `subprocess.run("a + b")` matches (a `+` sits inside the literal); the
    real-injection shape `subprocess.run("cmd " + arg)` does NOT, because the
    closing quote ends the `[^"']*` run before the `+`. This is a known
    weakness of the detector. The test pins the current behavior so a future
    regex change is a deliberate, reviewed decision rather than a silent one.
    """
    assert (
        "Subprocess with string concatenation"
        in _descriptions_for("python", 'subprocess.run("a + b")')
    )
    assert (
        "Subprocess with string concatenation"
        not in _descriptions_for("python", 'subprocess.run("cmd " + arg)')
    )


def test_commented_out_code_is_still_flagged(tmp_path: Path) -> None:
    """Characterization: the line-based regex has no comment stripping, so a
    commented-out dangerous call is still reported.

    This is a known false-positive source. The test documents it; it does not
    bless it. If the detector later learns to skip comments, this assertion
    flips and the change is reviewable.
    """
    name = _write(
        tmp_path,
        "commented.py",
        "# subprocess.run(f'ls {x}')  # disabled for now\n",
    )
    vulns, _ = scanner.scan_file(str(tmp_path / name))
    assert len(vulns) == 1
    assert vulns[0].cwe == "CWE-78"


# ---------------------------------------------------------------------------
# One vulnerability per line: scan_file breaks after the first match
# ---------------------------------------------------------------------------


def test_scan_file_reports_one_vulnerability_per_line(tmp_path: Path) -> None:
    """A bash line can match both the command-substitution and the
    unquoted-variable patterns. `scan_file` `break`s after the first match,
    so it reports exactly one finding for that line."""
    name = _write(tmp_path, "multi.sh", "result=$( $userInput )\n")
    vulns, _ = scanner.scan_file(str(tmp_path / name))
    assert len(vulns) == 1


# ---------------------------------------------------------------------------
# Suppression mechanism
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "cwe", "expected"),
    [
        ("eval(user_input)  # security-scan: ignore CWE-78", "CWE-78", True),
        ("eval(user_input)  # security-scan: ignore CWE-22", "CWE-78", False),
        ("eval(user_input)  # SECURITY-SCAN: IGNORE cwe-78", "CWE-78", True),
        ("eval(user_input)", "CWE-78", False),
        ("eval(user_input)  # ignore CWE-78", "CWE-78", False),
    ],
)
def test_is_line_suppressed(line: str, cwe: str, expected: bool) -> None:
    assert scanner.is_line_suppressed(line, cwe) is expected


def test_correct_suppression_moves_finding_to_suppressed(tmp_path: Path) -> None:
    name = _write(
        tmp_path,
        "suppressed.py",
        "eval(user_input)  # security-scan: ignore CWE-78\n",
    )
    vulns, suppressed = scanner.scan_file(str(tmp_path / name))
    assert vulns == []
    assert len(suppressed) == 1
    assert "CWE-78 suppressed" in suppressed[0]
    assert "suppressed.py:1" in suppressed[0]


def test_wrong_cwe_suppression_does_not_silence_finding(tmp_path: Path) -> None:
    """A suppression for the wrong CWE must NOT hide a CWE-78 finding."""
    name = _write(
        tmp_path,
        "wrong_suppress.py",
        "eval(user_input)  # security-scan: ignore CWE-22\n",
    )
    vulns, suppressed = scanner.scan_file(str(tmp_path / name))
    assert len(vulns) == 1
    assert suppressed == []


# ---------------------------------------------------------------------------
# scan_file edge cases
# ---------------------------------------------------------------------------


def test_scan_file_unsupported_extension_returns_empty(tmp_path: Path) -> None:
    name = _write(tmp_path, "readme.txt", "subprocess.run(f'ls {x}')\n")
    vulns, suppressed = scanner.scan_file(str(tmp_path / name))
    assert vulns == []
    assert suppressed == []


def test_scan_file_missing_file_returns_error(tmp_path: Path) -> None:
    target = tmp_path / "does_not_exist.py"
    vulns, errors = scanner.scan_file(str(target))
    assert vulns == []
    assert len(errors) == 1
    assert "Error reading" in errors[0]


def test_scan_file_clean_python_file_has_no_findings(tmp_path: Path) -> None:
    name = _write(
        tmp_path,
        "clean.py",
        "def add(a: int, b: int) -> int:\n    return a + b\n",
    )
    vulns, suppressed = scanner.scan_file(str(tmp_path / name))
    assert vulns == []
    assert suppressed == []


def test_cwe_filter_excluding_78_skips_detection(tmp_path: Path) -> None:
    """`scan_file(..., cwe_filter=[22])` must not run the CWE-78 patterns."""
    name = _write(tmp_path, "filtered.py", "eval(user_input)\n")
    vulns, _ = scanner.scan_file(str(tmp_path / name), cwe_filter=[22])
    assert vulns == []


def test_cwe_filter_including_78_runs_detection(tmp_path: Path) -> None:
    name = _write(tmp_path, "included.py", "eval(user_input)\n")
    vulns, _ = scanner.scan_file(str(tmp_path / name), cwe_filter=[78])
    assert len(vulns) == 1


# ---------------------------------------------------------------------------
# CLI exit codes (observed via subprocess; complements test_security_scan_cli)
# ---------------------------------------------------------------------------


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCANNER_PATH), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )


def test_cli_exit_success_on_clean_file(tmp_path: Path) -> None:
    name = _write(tmp_path, "ok.py", "x = 1 + 1\n")
    result = _run_cli(name, cwd=tmp_path)
    assert result.returncode == scanner.EXIT_SUCCESS
    assert "No vulnerabilities found" in result.stdout


def test_cli_exit_vulnerabilities_on_dirty_file(tmp_path: Path) -> None:
    name = _write(tmp_path, "bad.py", "subprocess.run(cmd, shell=True)\n")
    result = _run_cli(name, cwd=tmp_path)
    assert result.returncode == scanner.EXIT_VULNERABILITIES
    assert "CWE-78" in result.stdout
    assert "Command Injection" in result.stdout


def test_cli_console_exit_line_matches_errors_with_findings(tmp_path: Path) -> None:
    name = _write(tmp_path, "bad.py", "subprocess.run(cmd, shell=True)\n")
    result = _run_cli(name, "missing.py", cwd=tmp_path)

    assert result.returncode == scanner.EXIT_ERROR
    assert "Errors:" in result.stdout
    assert "Error reading missing.py" in result.stdout
    assert "Exit code: 1 (scan error)" in result.stdout
    assert "CWE-78" in result.stdout
    assert "Exit code: 1 (scan error)" in result.stdout


def test_cli_exit_error_when_no_files_given(tmp_path: Path) -> None:
    result = _run_cli(cwd=tmp_path)
    assert result.returncode == scanner.EXIT_ERROR
    assert "No files to scan" in result.stdout


def test_cli_exit_success_when_only_unsupported_files(tmp_path: Path) -> None:
    name = _write(tmp_path, "notes.txt", "subprocess.run(cmd, shell=True)\n")
    result = _run_cli(name, cwd=tmp_path)
    assert result.returncode == scanner.EXIT_SUCCESS
    assert "No supported files found" in result.stdout


def test_cli_exit_error_when_supported_file_cannot_be_read(tmp_path: Path) -> None:
    result = _run_cli("missing.py", cwd=tmp_path)

    assert result.returncode == scanner.EXIT_ERROR
    assert "Errors:" in result.stdout
    assert "Error reading missing.py" in result.stdout


def test_cli_json_reports_read_errors_fail_closed(tmp_path: Path) -> None:
    result = _run_cli("--format", "json", "missing.py", cwd=tmp_path)

    assert result.returncode == scanner.EXIT_ERROR
    payload = json.loads(result.stdout)
    assert payload["exit_code"] == scanner.EXIT_ERROR
    assert len(payload["errors"]) == 1
    assert payload["errors"][0].startswith("Error reading missing.py:")


def test_cli_json_output_reports_findings(tmp_path: Path) -> None:
    name = _write(tmp_path, "bad.py", "eval(user_input)\n")
    result = _run_cli("--format", "json", name, cwd=tmp_path)
    assert result.returncode == scanner.EXIT_VULNERABILITIES
    payload = json.loads(result.stdout)
    assert payload["files_scanned"] == 1
    assert len(payload["vulnerabilities"]) == 1
    assert payload["vulnerabilities"][0]["cwe"] == "CWE-78"
    assert payload["summary"]["by_cwe"]["CWE-78"] == 1
    assert payload["exit_code"] == scanner.EXIT_VULNERABILITIES
    # Pin the JSON envelope contract so schema changes are deliberate and
    # reviewable for this security-critical scanner: the version marker and the
    # delegated-CWE map that tells consumers CWE-22 is handled by CodeQL, not here.
    assert payload["schema_version"] == scanner._JSON_SCHEMA_VERSION
    delegated = payload["summary"]["delegated_cwes"]["CWE-22"]
    assert delegated["tool"] == "codeql"
    assert delegated["workflow"] == ".github/workflows/codeql-analysis.yml"


def test_cli_suppressed_finding_exits_success(tmp_path: Path) -> None:
    name = _write(
        tmp_path,
        "supp.py",
        "eval(user_input)  # security-scan: ignore CWE-78\n",
    )
    result = _run_cli(name, cwd=tmp_path)
    assert result.returncode == scanner.EXIT_SUCCESS
    assert "Suppressed findings: 1" in result.stdout


def test_cli_directory_scan_finds_nested_file(tmp_path: Path) -> None:
    nested = tmp_path / "src"
    nested.mkdir()
    (nested / "dirty.sh").write_text('eval "$cmd"\n', encoding="utf-8")
    result = _run_cli("--directory", "src", cwd=tmp_path)
    assert result.returncode == scanner.EXIT_VULNERABILITIES
    assert "CWE-78" in result.stdout


def test_cli_directory_scan_finds_extensionless_bash_hook(tmp_path: Path) -> None:
    hooks = tmp_path / ".githooks"
    hooks.mkdir()
    (hooks / "pre-push").write_text(
        "#!/usr/bin/env bash\neval \"$cmd\"\n",
        encoding="utf-8",
    )

    result = _run_cli("--directory", ".githooks", cwd=tmp_path)

    assert result.returncode == scanner.EXIT_VULNERABILITIES
    assert "pre-push:2" in result.stdout
    assert "CWE-78" in result.stdout


def test_cli_explicit_extensionless_bash_hook_is_scanned(tmp_path: Path) -> None:
    name = _write(
        tmp_path,
        "pre-commit",
        "#!/bin/bash\neval \"$cmd\"\n",
    )

    result = _run_cli(name, cwd=tmp_path)

    assert result.returncode == scanner.EXIT_VULNERABILITIES
    assert "pre-commit:2" in result.stdout
    assert "CWE-78" in result.stdout


def test_cli_output_file_written(tmp_path: Path) -> None:
    name = _write(tmp_path, "bad.py", "eval(user_input)\n")
    result = _run_cli("--format", "json", "--output", "out.json", name, cwd=tmp_path)
    assert result.returncode == scanner.EXIT_VULNERABILITIES
    out = tmp_path / "out.json"
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert len(payload["vulnerabilities"]) == 1


# In-process CLI (main) coverage.
#
# The exit-code tests above run the scanner as a subprocess, which exercises the
# real entry point but does not count toward in-process line coverage for this
# security-critical module. The tests below invoke `scanner.main()` directly with
# a patched argv so the argument handling, the --cwe delegation notice, and the
# path-traversal guard are covered in-process. `main()` calls `sys.exit()`, so
# each case asserts on the raised `SystemExit`.


def _run_main_in_process(
    monkeypatch: pytest.MonkeyPatch, *args: str, cwd: Path
) -> int:
    """Invoke scanner.main() in-process under cwd with argv=args; return exit code."""
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(sys, "argv", ["scan_vulnerabilities.py", *args])
    with pytest.raises(SystemExit) as excinfo:
        scanner.main()
    code = excinfo.value.code
    return 0 if code is None else int(code)


def test_main_cwe22_warns_and_notes_delegation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange: a clean supported file so the scan succeeds with no findings.
    _write(tmp_path, "clean.py", 'subprocess.run(["ls", "-l"])\n')
    # Act
    code = _run_main_in_process(monkeypatch, "--cwe", "22", "clean.py", cwd=tmp_path)
    captured = capsys.readouterr()
    # Assert: --cwe 22 is accepted (no error exit) but warns on stderr and notes
    # the CodeQL delegation in stdout, so a zero-finding result is not mistaken
    # for path-traversal coverage.
    assert code == scanner.EXIT_SUCCESS
    assert "WARNING: --cwe 22" in captured.err
    assert "CWE-22: delegated to CodeQL" in captured.out


def test_main_unsupported_cwe_exits_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "clean.py", 'subprocess.run(["ls", "-l"])\n')
    code = _run_main_in_process(monkeypatch, "--cwe", "99", "clean.py", cwd=tmp_path)
    captured = capsys.readouterr()
    assert code == scanner.EXIT_ERROR
    assert "not supported by this" in captured.err


def test_main_directory_path_traversal_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange: cwd is a nested dir so "../" escapes the allowed base.
    work = tmp_path / "work"
    work.mkdir()
    # Act
    code = _run_main_in_process(monkeypatch, "--directory", "../outside", cwd=work)
    captured = capsys.readouterr()
    # Assert: containment check rejects the escaping --directory with EXIT_ERROR.
    assert code == scanner.EXIT_ERROR
    assert "Path traversal" in captured.err


def test_main_git_staged_scans_staged_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange: a vulnerable staged file, with get_staged_files stubbed so the test
    # does not depend on a real git index.
    name = _write(tmp_path, "staged.py", "subprocess.run(cmd, shell=True)\n")
    monkeypatch.setattr(scanner, "get_staged_files", lambda: [name])
    # Act
    code = _run_main_in_process(monkeypatch, "--git-staged", cwd=tmp_path)
    captured = capsys.readouterr()
    # Assert: --git-staged feeds the staged file into the scan and reports CWE-78.
    assert code == scanner.EXIT_VULNERABILITIES
    assert "CWE-78" in captured.out


def test_main_git_staged_no_files_exits_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(scanner, "get_staged_files", lambda: [])
    code = _run_main_in_process(monkeypatch, "--git-staged", cwd=tmp_path)
    captured = capsys.readouterr()
    assert code == scanner.EXIT_ERROR
    assert "No files to scan" in captured.out


def test_main_json_format_in_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange: a vulnerable file so the JSON envelope carries a finding.
    name = _write(tmp_path, "vuln.py", "subprocess.run(cmd, shell=True)\n")
    # Act: exercise format_json_output() in-process (subprocess-only before).
    code = _run_main_in_process(
        monkeypatch, "--format", "json", name, cwd=tmp_path
    )
    captured = capsys.readouterr()
    # Assert: pinned envelope shape, a CWE-78 finding, and the delegated-CWE map.
    assert code == scanner.EXIT_VULNERABILITIES
    data = json.loads(captured.out)
    assert data["schema_version"] == scanner._JSON_SCHEMA_VERSION
    assert data["files_scanned"] == 1
    assert data["summary"]["total"] >= 1
    assert data["summary"]["by_cwe"].get("CWE-78", 0) >= 1
    assert any(v["cwe"] == "CWE-78" for v in data["vulnerabilities"])
    assert data["summary"]["delegated_cwes"]["CWE-22"]["tool"] == "codeql"


def test_main_directory_scan_in_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange: a nested project dir with one vulnerable file, so the successful
    # get_directory_files() walk is exercised in-process (subprocess-only before).
    proj = tmp_path / "proj"
    (proj / "pkg").mkdir(parents=True)
    (proj / "pkg" / "vuln.py").write_text(
        "subprocess.run(cmd, shell=True)\n", encoding="utf-8"
    )
    (proj / "notes.txt").write_text("not scannable\n", encoding="utf-8")
    # Act: cwd is tmp_path so the relative --directory passes the containment guard.
    code = _run_main_in_process(
        monkeypatch, "--directory", "proj", cwd=tmp_path
    )
    captured = capsys.readouterr()
    # Assert: the directory walk found and scanned only the supported file and
    # reported the CWE-78 finding.
    assert code == scanner.EXIT_VULNERABILITIES
    assert "CWE-78" in captured.out


# ---------------------------------------------------------------------------
# Extensionless shebang detection (issue #2367)
# ---------------------------------------------------------------------------
# .githooks/pre-push and other extensionless executables advertise their
# interpreter only via a shebang. The detector must read the first line and
# treat bash/sh-family shebangs as bash, otherwise high-risk shell entry
# points are silently skipped under `.githooks/**` per
# `.github/instructions/security.instructions.md`.


@pytest.mark.parametrize(
    ("shebang", "expected"),
    [
        ("#!/usr/bin/env bash\n", "bash"),
        ("#!/usr/bin/env -S bash\n", "bash"),
        ("#!/usr/bin/env -i sh\n", "bash"),
        ("#!/bin/bash\n", "bash"),
        ("#!/bin/sh\n", "bash"),
        ("#!/usr/bin/env sh\n", "bash"),
        ("#! /usr/bin/env bash\n", "bash"),
        ("#!/usr/bin/env dash\n", "bash"),
        ("#!/usr/bin/env ksh\n", "bash"),
        ("#!/usr/bin/env python3\n", None),
        ("#!/usr/bin/env -S python3\n", None),
        ("#!/usr/bin/env node\n", None),
        ("#!/usr/bin/env pwsh\n", None),
        ("plain text, no shebang\n", None),
        ("", None),
    ],
)
def test_get_language_shebang_fallback(
    tmp_path: Path, shebang: str, expected: str | None
) -> None:
    """Extensionless files classify by shebang interpreter; non-shell shebangs reject."""
    f = tmp_path / "pre-push"
    f.write_text(shebang + "echo hi\n", encoding="utf-8")
    assert scanner.get_language(str(f)) == expected


def test_get_language_extension_wins_over_shebang(tmp_path: Path) -> None:
    """A known suffix never triggers the shebang path; suffix is authoritative."""
    f = tmp_path / "thing.txt"
    f.write_text("#!/usr/bin/env bash\necho hi\n", encoding="utf-8")
    assert scanner.get_language(str(f)) is None


def test_get_language_missing_file_returns_none(tmp_path: Path) -> None:
    """Unreadable extensionless paths don't raise; they classify as unsupported."""
    assert scanner.get_language(str(tmp_path / "does-not-exist")) is None


def test_get_language_invalid_utf8_shebang_returns_none(tmp_path: Path) -> None:
    """Invalid UTF-8 in a shebang is treated as unsupported, not replaced."""
    hook = tmp_path / "pre-push"
    hook.write_bytes(b"#!\xff\xfe\n")
    assert scanner.get_language(str(hook)) is None


def test_get_directory_files_includes_extensionless_bash(tmp_path: Path) -> None:
    """Directory walk surfaces extensionless bash scripts under `.githooks/`-style layouts."""
    hooks = tmp_path / ".githooks"
    hooks.mkdir()
    bash_hook = hooks / "pre-push"
    bash_hook.write_text("#!/usr/bin/env bash\necho hi\n", encoding="utf-8")
    (hooks / "README").write_text("just docs\n", encoding="utf-8")
    py_hook = hooks / "py-hook"
    py_hook.write_text("#!/usr/bin/env python3\nprint('x')\n", encoding="utf-8")

    found = scanner.get_directory_files(str(tmp_path))
    assert str(bash_hook) in found
    assert str(hooks / "README") not in found
    assert str(py_hook) not in found


def test_get_directory_files_prunes_noisy_directories(tmp_path: Path) -> None:
    """Directory walk skips dependency and metadata trees before shebang reads."""
    git_objects = tmp_path / ".git" / "objects"
    git_objects.mkdir(parents=True)
    git_object = git_objects / "abcdef"
    git_object.write_text("#!/usr/bin/env bash\neval $payload\n", encoding="utf-8")

    node_bin = tmp_path / "node_modules" / ".bin"
    node_bin.mkdir(parents=True)
    node_script = node_bin / "tool"
    node_script.write_text("#!/usr/bin/env bash\neval $payload\n", encoding="utf-8")

    mixed_case = tmp_path / "Node_Modules" / ".bin"
    mixed_case.mkdir(parents=True)
    mixed_case_script = mixed_case / "tool"
    mixed_case_script.write_text(
        "#!/usr/bin/env bash\neval $payload\n", encoding="utf-8"
    )

    hooks = tmp_path / ".githooks"
    hooks.mkdir()
    hook = hooks / "pre-push"
    hook.write_text("#!/usr/bin/env bash\neval $payload\n", encoding="utf-8")

    found = scanner.get_directory_files(str(tmp_path))

    assert str(hook) in found
    assert str(git_object) not in found
    assert str(node_script) not in found
    assert str(mixed_case_script) not in found


def test_scan_extensionless_bash_hook_emits_cwe78(tmp_path: Path) -> None:
    """End-to-end: an extensionless bash hook with a CWE-78 pattern is detected."""
    hook = tmp_path / "pre-push"
    hook.write_text(
        "#!/usr/bin/env bash\n"
        "FILE=$1\n"
        'echo "running $FILE"\n'
        "eval $FILE\n",
        encoding="utf-8",
    )
    vulns, _suppressed = scanner.scan_file(str(hook))
    assert any(v.cwe == "CWE-78" for v in vulns), (
        f"expected at least one CWE-78 finding, got {[v.cwe for v in vulns]}"
    )
