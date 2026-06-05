#!/usr/bin/env python3
"""
Security vulnerability scanner for CWE-78 (command injection).

Lightweight pattern-based detection for Python, PowerShell, Bash, and C# files.
Designed for pre-PR scanning and CI integration.

CWE-22 (path traversal) detection is delegated to CodeQL's
``python-security-extended`` query suite, which runs on every PR via
``.github/workflows/codeql-analysis.yml``. The internal regex-based scanner
was found to produce false positives on safe ``Path(__file__)`` derivations
(see issue #1843, PR #1841) without comparable coverage of real CWE-22
vectors. Per the buy-vs-build framework, CWE-22 is Context (table stakes
security, not a competitive differentiator) and CodeQL is the authoritative
detector already in the repo's CI pipeline.

Exit codes:
    0  - No vulnerabilities found
    1  - Scan error (file not found, invalid arguments)
    10 - Vulnerabilities detected

Usage:
    python scan_vulnerabilities.py --git-staged
    python scan_vulnerabilities.py --directory src/
    python scan_vulnerabilities.py file1.py file2.ps1
    python scan_vulnerabilities.py --format json --output results.json
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# Exit codes (ADR-035 compliant)
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_VULNERABILITIES = 10

# Suppression comment pattern
SUPPRESSION_PATTERN = re.compile(
    r"#\s*security-scan:\s*ignore\s+(CWE-\d+)",
    re.IGNORECASE,
)


@dataclass
class Vulnerability:
    """Represents a detected vulnerability."""

    cwe: str
    title: str
    file: str
    line: int
    code: str
    pattern: str
    severity: str
    recommendation: str


@dataclass
class ScanResult:
    """Scan result container."""

    scan_timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    files_scanned: int = 0
    vulnerabilities: list = field(default_factory=list)
    suppressed: list = field(default_factory=list)
    errors: list = field(default_factory=list)


# CWE-78: Command Injection patterns by language
CWE78_PATTERNS = {
    "python": [
        {
            "pattern": re.compile(
                r'subprocess\.(run|call|Popen|check_output|check_call)\s*\(\s*f["\']',
            ),
            "description": "Subprocess with f-string command (potential injection)",
            "severity": "CRITICAL",
            "recommendation": "Use list form of command arguments instead of shell string",
        },
        {
            "pattern": re.compile(
                r"subprocess\.(run|call|Popen|check_output|check_call)\s*\([^)]*shell\s*=\s*True",
            ),
            "description": "Subprocess with shell=True",
            "severity": "HIGH",
            "recommendation": "Avoid shell=True; use list form of command arguments",
        },
        {
            "pattern": re.compile(
                r'subprocess\.(run|call|Popen|check_output|check_call)\s*\(\s*["\'][^"\']*\s*\+',
            ),
            "description": "Subprocess with string concatenation",
            "severity": "CRITICAL",
            "recommendation": "Use list form of command arguments instead of string concatenation",
        },
        {
            "pattern": re.compile(
                r"eval\s*\(\s*(\w*(user|input|param|arg|request|cmd|command)\w*)",
                re.IGNORECASE,
            ),
            "description": "eval() with potentially unvalidated input",
            "severity": "CRITICAL",
            "recommendation": "Never use eval() with user input",
        },
        {
            "pattern": re.compile(
                r"exec\s*\(\s*(\w*(user|input|param|arg|request|cmd|command)\w*)",
                re.IGNORECASE,
            ),
            "description": "exec() with potentially unvalidated input",
            "severity": "CRITICAL",
            "recommendation": "Never use exec() with user input",
        },
    ],
    "powershell": [
        {
            "pattern": re.compile(
                r'Invoke-Expression\s+["\'][^"\']*\$(\w+)',
            ),
            "description": "Invoke-Expression with variable interpolation",
            "severity": "CRITICAL",
            "recommendation": (
                "Avoid Invoke-Expression; use direct cmdlet calls or & "
                "operator with validated arguments"
            ),
        },
        {
            "pattern": re.compile(
                r"Invoke-Expression\s+\$(\w*(user|input|param|arg|request|cmd|command)\w*)",
                re.IGNORECASE,
            ),
            "description": "Invoke-Expression with potentially unvalidated input",
            "severity": "CRITICAL",
            "recommendation": "Never use Invoke-Expression with user input",
        },
        {
            "pattern": re.compile(
                r"&\s+\$(\w*(user|input|param|arg|request|cmd|command)\w*)",
                re.IGNORECASE,
            ),
            "description": "Call operator with potentially unvalidated command",
            "severity": "HIGH",
            "recommendation": "Validate command before execution",
        },
        {
            "pattern": re.compile(
                r"Start-Process\s+[^-]*-ArgumentList\s+[^|]*\$(\w*(user|input|param|arg|request)\w*)",
                re.IGNORECASE,
            ),
            "description": "Start-Process with potentially unvalidated arguments",
            "severity": "HIGH",
            "recommendation": "Validate all arguments before passing to Start-Process",
        },
    ],
    "bash": [
        {
            "pattern": re.compile(
                r"eval\s+[\"']?\$",
            ),
            "description": "eval with variable expansion",
            "severity": "CRITICAL",
            "recommendation": "Avoid eval; use direct command execution with proper quoting",
        },
        {
            "pattern": re.compile(
                r"\$\(\s*\$(\w*(user|input|param|arg|request|cmd|command)\w*)",
                re.IGNORECASE,
            ),
            "description": "Command substitution with potentially unvalidated input",
            "severity": "CRITICAL",
            "recommendation": "Validate input before command substitution",
        },
        {
            "pattern": re.compile(
                r"`\s*\$(\w*(user|input|param|arg|request|cmd|command)\w*)",
                re.IGNORECASE,
            ),
            "description": "Backtick command substitution with potentially unvalidated input",
            "severity": "CRITICAL",
            "recommendation": "Validate input before command substitution; prefer $() syntax",
        },
        {
            "pattern": re.compile(
                r"(?<![\"'])\$\w+(?![\"'\w])",
            ),
            "description": "Unquoted variable expansion (potential word splitting/injection)",
            "severity": "MEDIUM",
            "recommendation": 'Quote all variable expansions: use "$var" instead of $var',
        },
    ],
    "csharp": [
        {
            "pattern": re.compile(
                r"Process\.Start\s*\([^)]*(\w*(user|input|param|arg|request|cmd|command)\w*)",
                re.IGNORECASE,
            ),
            "description": "Process.Start with potentially unvalidated command",
            "severity": "HIGH",
            "recommendation": "Validate command and arguments before execution",
        },
        {
            "pattern": re.compile(
                r'ProcessStartInfo\s*\{[^}]*Arguments\s*=\s*\$"',
            ),
            "description": "ProcessStartInfo with interpolated arguments",
            "severity": "HIGH",
            "recommendation": (
                "Validate all arguments; avoid string interpolation in "
                "command arguments"
            ),
        },
        {
            "pattern": re.compile(
                r'new\s+Process\s*\(\s*\)\s*\{[^}]*FileName\s*=\s*(\w*(user|input|param|arg|request|cmd)\w*)',
                re.IGNORECASE,
            ),
            "description": "Process with potentially unvalidated FileName",
            "severity": "HIGH",
            "recommendation": "Validate FileName before process creation",
        },
    ],
}


# Shebang interpreters that resolve to bash for this scanner. Matches
# `#!/bin/sh`, `#!/bin/bash`, `#!/usr/bin/env bash`, `#!/usr/bin/env sh`,
# etc. POSIX `sh` is included because the CWE-78 patterns this scanner
# uses (command substitution, eval, unquoted `$VAR` in shell commands)
# apply equally to POSIX shell scripts.
_BASH_SHEBANG_RE = re.compile(
    r"^#!\s*(?:/usr/bin/env\s+)?(?:[\w./-]*/)?(?:ba|da|k|a)?sh\b"
)


def _detect_shebang_language(file_path: str) -> str | None:
    """Read the first line of ``file_path`` and classify by shebang.

    Returns the scanner language name (e.g. ``"bash"``) or ``None`` if
    the file is unreadable, has no shebang, or names an interpreter the
    scanner doesn't support. Extensionless scripts such as git hooks
    (``.githooks/pre-push``) rely on this path to be scanned at all.
    """
    try:
        with open(file_path, "rb") as f:
            # 256 bytes is enough for any realistic shebang line.
            head = f.read(256)
    except (FileNotFoundError, PermissionError, IsADirectoryError, OSError):
        return None
    if not head.startswith(b"#!"):
        return None
    try:
        first_line = head.split(b"\n", 1)[0].decode("utf-8", errors="replace")
    except UnicodeDecodeError:
        return None
    if _BASH_SHEBANG_RE.match(first_line):
        return "bash"
    return None


def get_language(file_path: str) -> str | None:
    """Detect language from file extension, falling back to shebang.

    Extensionless executable scripts (notably git hooks under
    ``.githooks/``) carry no suffix but advertise their interpreter via
    a shebang. When the suffix lookup yields nothing, peek at the
    file's first line so Bash entry points aren't silently skipped.
    """
    ext = Path(file_path).suffix.lower()
    language_map = {
        ".py": "python",
        ".ps1": "powershell",
        ".psm1": "powershell",
        ".sh": "bash",
        ".bash": "bash",
        ".cs": "csharp",
    }
    lang = language_map.get(ext)
    if lang is not None:
        return lang
    # Only consult the shebang for truly extensionless files. Files
    # with an unknown suffix (e.g. `notes.txt`, `Dockerfile.bak`) are
    # intentionally rejected so we don't broaden the scanner surface
    # by accident.
    if ext == "":
        return _detect_shebang_language(file_path)
    return None


def get_staged_files() -> list[str]:
    """Get list of staged files from git.

    Note: Uses subprocess with fixed arguments (no user input) - safe from injection.
    """
    try:
        # Safe: fixed command with no user input
        result = subprocess.run(
            ["git", "diff", "--staged", "--name-only"],
            capture_output=True,
            text=True,
            check=True,
        )
        return [f for f in result.stdout.strip().split("\n") if f]
    except subprocess.CalledProcessError:
        return []


def get_directory_files(directory: str) -> list[str]:
    """Get all scannable files from a directory.

    Files with a known suffix are included by extension. Extensionless
    files are included only when their shebang resolves to a supported
    interpreter (currently bash/sh family). This keeps `.githooks/`
    coverage symmetric with single-file scans of the same paths.
    """
    supported_extensions = {".py", ".ps1", ".psm1", ".sh", ".bash", ".cs"}
    files = []
    for root, _, filenames in os.walk(directory):
        for filename in filenames:
            full_path = os.path.join(root, filename)
            ext = Path(filename).suffix.lower()
            if ext in supported_extensions:
                files.append(full_path)
            elif ext == "" and _detect_shebang_language(full_path) is not None:
                files.append(full_path)
    return files


def is_line_suppressed(line: str, cwe: str) -> bool:
    """Check if a line has a suppression comment for the given CWE."""
    match = SUPPRESSION_PATTERN.search(line)
    if match:
        suppressed_cwe = match.group(1).upper()
        return suppressed_cwe == cwe.upper()
    return False


def scan_file(
    file_path: str, cwe_filter: list[int] | None = None
) -> tuple[list[Vulnerability], list[str]]:
    """Scan a single file for vulnerabilities."""
    vulnerabilities: list[Vulnerability] = []
    suppressed: list[str] = []

    language = get_language(file_path)
    if not language:
        return vulnerabilities, suppressed

    try:
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except (FileNotFoundError, PermissionError) as e:
        return vulnerabilities, [f"Error reading {file_path}: {e}"]

    # Get patterns for this language. CWE-22 detection is delegated to CodeQL
    # (`.github/workflows/codeql-analysis.yml` runs `python-security-extended.qls`
    # on every PR); see this module's docstring for the buy-vs-build rationale.
    cwe78_patterns = CWE78_PATTERNS.get(language, [])

    for line_num, line in enumerate(lines, 1):
        # Check CWE-78 patterns
        if cwe_filter is None or 78 in cwe_filter:
            for pattern_info in cwe78_patterns:
                pattern = pattern_info["pattern"]
                if not isinstance(pattern, re.Pattern):
                    continue
                if pattern.search(line):
                    if is_line_suppressed(line, "CWE-78"):
                        suppressed.append(f"CWE-78 suppressed at {file_path}:{line_num}")
                    else:
                        vulnerabilities.append(
                            Vulnerability(
                                cwe="CWE-78",
                                title="Command Injection Vulnerability",
                                file=file_path,
                                line=line_num,
                                code=line.strip()[:200],
                                pattern=str(pattern_info["description"]),
                                severity=str(pattern_info["severity"]),
                                recommendation=str(pattern_info["recommendation"]),
                            )
                        )
                    break

    return vulnerabilities, suppressed


def format_console_output(result: ScanResult) -> str:
    """Format scan result for console output."""
    output = ["=== Security Vulnerability Scan ===", ""]

    if result.errors:
        output.append("Errors:")
        for error in result.errors:
            output.append(f"  {error}")
        output.append("")

    if not result.vulnerabilities:
        output.append(f"Files scanned: {result.files_scanned}")
        output.append("No vulnerabilities found.")
        if result.suppressed:
            output.append(f"Suppressed findings: {len(result.suppressed)}")
        return "\n".join(output)

    # Group by severity
    by_severity: dict[str, list[Vulnerability]] = {
        "CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": []
    }
    for vuln in result.vulnerabilities:
        by_severity.get(vuln.severity, by_severity["MEDIUM"]).append(vuln)

    for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        for vuln in by_severity[severity]:
            output.append(f"[{vuln.cwe}] {vuln.title}")
            output.append(f"  File: {vuln.file}:{vuln.line}")
            output.append(f"  Pattern: {vuln.pattern}")
            output.append(f"  Code: {vuln.code}")
            output.append(f"  Severity: {vuln.severity}")
            output.append(f"  Recommendation: {vuln.recommendation}")
            output.append("")

    # Summary
    output.append("=== Summary ===")
    output.append(f"Files scanned: {result.files_scanned}")
    output.append(f"Vulnerabilities found: {len(result.vulnerabilities)}")

    cwe_counts: dict[str, int] = {}
    for vuln in result.vulnerabilities:
        cwe_counts[vuln.cwe] = cwe_counts.get(vuln.cwe, 0) + 1
    for cwe, count in sorted(cwe_counts.items()):
        output.append(f"  {cwe} (Command Injection): {count}")

    if result.suppressed:
        output.append(f"Suppressed findings: {len(result.suppressed)}")

    output.append("")
    output.append(f"Exit code: {EXIT_VULNERABILITIES} (vulnerabilities detected)")

    return "\n".join(output)


_JSON_SCHEMA_VERSION = 2


def format_json_output(result: ScanResult) -> str:
    """Format scan result as JSON.

    The output envelope carries `schema_version` so downstream consumers can
    detect schema evolution. Readers MUST tolerate unknown fields and treat
    the absence of `schema_version` as v1 (pre-CWE-22-delegation, no
    `summary.delegated_cwes` field). v2 added `summary.delegated_cwes` when
    CWE-22 detection moved to CodeQL (PR #1851, see
    `.agents/architecture/ADR-054-local-security-scanning.md` amendment).
    """
    by_cwe: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    summary = {
        "total": len(result.vulnerabilities),
        "by_cwe": by_cwe,
        "by_severity": by_severity,
        # Delegated CWE classes — this scanner does not detect them; the named
        # detector does. A `summary.by_cwe.get("CWE-22", 0) == 0` reading from
        # this scanner means "not detected here", NOT "no findings"; use the
        # delegated detector's report for authoritative coverage. Each entry
        # is self-describing: `tool` names the detector, `query` names the
        # specific rule pack, `workflow` cites where it runs.
        "delegated_cwes": {
            "CWE-22": {
                "tool": "codeql",
                "query": "python-security-extended.qls",
                "workflow": ".github/workflows/codeql-analysis.yml",
            },
        },
    }
    output = {
        "schema_version": _JSON_SCHEMA_VERSION,
        "scan_timestamp": result.scan_timestamp,
        "files_scanned": result.files_scanned,
        "vulnerabilities": [
            {
                "cwe": v.cwe,
                "title": v.title,
                "file": v.file,
                "line": v.line,
                "code": v.code,
                "pattern": v.pattern,
                "severity": v.severity,
                "recommendation": v.recommendation,
            }
            for v in result.vulnerabilities
        ],
        "suppressed": result.suppressed,
        "errors": result.errors,
        "summary": summary,
        "exit_code": EXIT_VULNERABILITIES if result.vulnerabilities else EXIT_SUCCESS,
    }

    for vuln in result.vulnerabilities:
        by_cwe[vuln.cwe] = by_cwe.get(vuln.cwe, 0) + 1
        by_severity[vuln.severity] = by_severity.get(vuln.severity, 0) + 1

    return json.dumps(output, indent=2)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scan code for CWE-78 (command injection). CWE-22 path-traversal "
                    "detection is delegated to CodeQL in CI; see module docstring.",
        epilog=(
            "Exit codes:\n"
            "  0  no vulnerabilities found\n"
            "  1  scan error (invalid args, file not found, path traversal)\n"
            "  10 vulnerabilities detected (CI-blocking)\n"
            "\n"
            "See .agents/architecture/ADR-054-local-security-scanning.md."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Files to scan",
    )
    parser.add_argument(
        "--git-staged",
        action="store_true",
        help="Scan git staged files",
    )
    parser.add_argument(
        "--directory",
        "-d",
        help="Scan all supported files in directory",
    )
    parser.add_argument(
        "--cwe",
        type=int,
        action="append",
        help=(
            "Filter by CWE number (only 78 is supported by this scanner). "
            "CWE-22 is accepted but produces no findings here; detection is "
            "delegated to CodeQL. "
            "(Sunset: the CWE-22 flag may be removed after 2026-08-01.)"
        ),
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["console", "json"],
        default="console",
        help="Output format",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file (default: stdout)",
    )

    args = parser.parse_args()

    # Surface a deprecation-style notice when --cwe 22 is requested. The flag is
    # accepted for backward compatibility with CI invocations but produces no
    # findings here; CWE-22 detection is delegated to CodeQL. Without this
    # warning, a caller could mis-read the silent zero-finding result as a
    # clean bill of health for path traversal.
    # Validate --cwe values. The scanner only detects CWE-78; CWE-22 is
    # accepted for backward compatibility (with a stderr warning) and any
    # other value is a typo that would otherwise produce a misleading
    # zero-finding result.
    _SUPPORTED_CWES = {78}
    _DELEGATED_CWES = {22}
    if args.cwe:
        unsupported = set(args.cwe) - _SUPPORTED_CWES - _DELEGATED_CWES
        if unsupported:
            print(
                f"ERROR: --cwe {sorted(unsupported)} not supported by this "
                f"scanner. Supported: {sorted(_SUPPORTED_CWES)} "
                f"(delegated to other tools: {sorted(_DELEGATED_CWES)}).",
                file=sys.stderr,
            )
            sys.exit(EXIT_ERROR)
        if 22 in args.cwe:
            print(
                "WARNING: --cwe 22 selected but CWE-22 detection is delegated to "
                "CodeQL (see python-security-extended.qls in "
                ".github/workflows/codeql-analysis.yml). This scanner reports no "
                "CWE-22 findings; rely on the CodeQL workflow for path-traversal "
                "coverage. If CodeQL flags a CWE-22 finding on your PR, fix the "
                "code, or add a `lgtm[py/path-injection]` suppression comment "
                "with justification per CodeQL docs.",
                file=sys.stderr,
            )

    # Validate input paths to prevent path traversal (CWE-22).
    #
    # Use Path.resolve() to follow symlinks AND normalize, then
    # Path.is_relative_to() for componentwise containment. The earlier
    # implementation used os.path.abspath + str.startswith, which had two
    # gaps: (a) abspath does not follow symlinks, so a symlink inside the
    # cwd could point outside; (b) startswith matches by string prefix, so
    # `/foo/barevil` would falsely satisfy a check against `/foo/bar`.
    # is_relative_to is path-component aware and Python 3.10+ stdlib (the
    # project requires 3.10+ per pyproject.toml).
    try:
        allowed_base = Path(".").resolve(strict=False)

        def _validate_path(raw: str, label: str) -> None:
            candidate = Path(raw).resolve(strict=False)
            if not candidate.is_relative_to(allowed_base):
                raise ValueError(
                    f"Path traversal attempt detected in {label}: {raw}"
                )

        if args.directory:
            _validate_path(args.directory, "--directory")
        if args.output:
            _validate_path(args.output, "--output")
        if args.files:
            for file in args.files:
                _validate_path(file, "file")
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(EXIT_ERROR)

    # Collect files to scan
    files_to_scan = []

    if args.git_staged:
        files_to_scan.extend(get_staged_files())

    if args.directory:
        files_to_scan.extend(get_directory_files(args.directory))

    if args.files:
        files_to_scan.extend(args.files)

    if not files_to_scan:
        print("No files to scan. Use --git-staged, --directory, or specify files.")
        sys.exit(EXIT_ERROR)

    # Deduplicate
    files_to_scan = list(set(files_to_scan))

    # Filter by supported languages
    supported_files = [f for f in files_to_scan if get_language(f) is not None]

    if not supported_files:
        print("No supported files found (Python, PowerShell, Bash, C#).")
        sys.exit(EXIT_SUCCESS)

    # Scan files
    result = ScanResult()
    result.files_scanned = len(supported_files)

    for file_path in supported_files:
        vulns, suppressed = scan_file(file_path, args.cwe)
        result.vulnerabilities.extend(vulns)
        result.suppressed.extend(suppressed)

    # Format output
    if args.format == "json":
        output = format_json_output(result)
    else:
        output = format_console_output(result)
        # Surface CWE-22 delegation in console output too. The JSON envelope
        # carries `summary.delegated_cwes`, but a console caller running
        # `--cwe 22` should see the delegation in stdout, not just stderr.
        if args.cwe and 22 in args.cwe:
            output += (
                "\n\nCWE-22: delegated to CodeQL "
                "(see .github/workflows/codeql-analysis.yml)"
            )

    # Write output
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Results written to {args.output}")
    else:
        print(output)

    # Exit code
    if result.vulnerabilities:
        sys.exit(EXIT_VULNERABILITIES)
    sys.exit(EXIT_SUCCESS)


if __name__ == "__main__":
    main()
