#!/usr/bin/env python3
"""
Security vulnerability scanner for CWE-22 (path traversal) and CWE-78 (command injection).

Lightweight pattern-based detection for Python, PowerShell, Bash, and C# files.
Designed for pre-PR scanning and CI integration.

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


# CWE-22: Path Traversal patterns by language
CWE22_PATTERNS = {
    "python": [
        {
            "pattern": re.compile(
                r"os\.path\.join\s*\([^,]+,\s*(\w*(user|input|param|arg|request|path|file|name)\w*)",
                re.IGNORECASE,
            ),
            "description": "os.path.join with potentially unvalidated user input",
            "severity": "HIGH",
            "recommendation": (
                "Validate input does not contain '..' and use "
                "os.path.realpath() with containment check"
            ),
        },
        {
            "pattern": re.compile(
                r"open\s*\(\s*(\w*(user|input|param|arg|request|path|file|name)\w*)",
                re.IGNORECASE,
            ),
            "description": "File open with potentially unvalidated path",
            "severity": "HIGH",
            "recommendation": "Validate path is within allowed directory before opening",
        },
        {
            "pattern": re.compile(
                r"Path\s*\(\s*(\w*(user|input|param|arg|request|path|file|name)\w*)",
                re.IGNORECASE,
            ),
            "description": "pathlib.Path with potentially unvalidated input",
            "severity": "HIGH",
            "recommendation": "Use Path.resolve() and verify path is within allowed directory",
        },
        {
            "pattern": re.compile(
                r"(shutil\.(copy|move|rmtree)|os\.(remove|unlink|rename))\s*\([^)]*(\w*(user|input|param|arg|request|path|file)\w*)",
                re.IGNORECASE,
            ),
            "description": "File operation with potentially unvalidated path",
            "severity": "HIGH",
            "recommendation": "Validate all paths before file operations",
        },
    ],
    "powershell": [
        {
            "pattern": re.compile(
                r"Join-Path\s+[^-]+\s+\$(\w*(user|input|param|arg|request|path|file|name)\w*)",
                re.IGNORECASE,
            ),
            "description": "Join-Path with potentially unvalidated user input",
            "severity": "HIGH",
            "recommendation": "Validate input does not contain '..' before joining paths",
        },
        {
            "pattern": re.compile(
                r"(Get-Content|Set-Content|Remove-Item|Copy-Item|Move-Item)\s+[^|]*\$(\w*(user|input|param|arg|request|path|file|name)\w*)",
                re.IGNORECASE,
            ),
            "description": "File operation with potentially unvalidated path",
            "severity": "HIGH",
            "recommendation": "Use Resolve-Path and validate path is within allowed directory",
        },
        {
            "pattern": re.compile(
                r"\.\s+\$(\w*(user|input|param|arg|script|path|file)\w*)",
                re.IGNORECASE,
            ),
            "description": "Dot-sourcing with potentially unvalidated path",
            "severity": "CRITICAL",
            "recommendation": "Never dot-source user-provided paths",
        },
    ],
    "bash": [
        {
            "pattern": re.compile(
                r"(cat|head|tail|less|more|source|\.)\s+[\"']?\$\{?(\w*(user|input|param|arg|request|path|file|name)\w*)",
                re.IGNORECASE,
            ),
            "description": "File read with potentially unvalidated path",
            "severity": "HIGH",
            "recommendation": "Validate path does not contain '..' and is within allowed directory",
        },
        {
            "pattern": re.compile(
                r"(rm|mv|cp)\s+(-[rfv]+\s+)?[\"']?\$\{?(\w*(user|input|param|arg|request|path|file)\w*)",
                re.IGNORECASE,
            ),
            "description": "File operation with potentially unvalidated path",
            "severity": "HIGH",
            "recommendation": "Validate path before file operations",
        },
        {
            "pattern": re.compile(
                r"source\s+[\"']?\$",
                re.IGNORECASE,
            ),
            "description": "Sourcing script from variable path",
            "severity": "CRITICAL",
            "recommendation": "Never source user-provided script paths",
        },
    ],
    "csharp": [
        {
            "pattern": re.compile(
                r"Path\.Combine\s*\([^,]+,\s*(\w*(user|input|param|arg|request|path|file|name)\w*)",
                re.IGNORECASE,
            ),
            "description": "Path.Combine with potentially unvalidated user input",
            "severity": "HIGH",
            "recommendation": (
                "Use Path.GetFullPath() and verify path starts with allowed "
                "base directory"
            ),
        },
        {
            "pattern": re.compile(
                r"(File\.(ReadAllText|WriteAllText|Delete|Copy|Move)|Directory\.(Delete|Move))\s*\([^)]*(\w*(user|input|param|arg|request|path|file)\w*)",
                re.IGNORECASE,
            ),
            "description": "File operation with potentially unvalidated path",
            "severity": "HIGH",
            "recommendation": "Validate path is within allowed directory before file operations",
        },
        {
            "pattern": re.compile(
                r"new\s+FileStream\s*\([^)]*(\w*(user|input|param|arg|request|path|file)\w*)",
                re.IGNORECASE,
            ),
            "description": "FileStream with potentially unvalidated path",
            "severity": "HIGH",
            "recommendation": "Validate path before creating FileStream",
        },
    ],
}

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


def get_language(file_path: str) -> str | None:
    """Detect language from file extension."""
    ext = Path(file_path).suffix.lower()
    language_map = {
        ".py": "python",
        ".ps1": "powershell",
        ".psm1": "powershell",
        ".sh": "bash",
        ".bash": "bash",
        ".cs": "csharp",
    }
    return language_map.get(ext)


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
    """Get all scannable files from a directory."""
    supported_extensions = {".py", ".ps1", ".psm1", ".sh", ".bash", ".cs"}
    files = []
    for root, _, filenames in os.walk(directory):
        for filename in filenames:
            if Path(filename).suffix.lower() in supported_extensions:
                files.append(os.path.join(root, filename))
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

    # Get patterns for this language
    cwe22_patterns = CWE22_PATTERNS.get(language, [])
    cwe78_patterns = CWE78_PATTERNS.get(language, [])

    for line_num, line in enumerate(lines, 1):
        # Check CWE-22 patterns
        if cwe_filter is None or 22 in cwe_filter:
            for pattern_info in cwe22_patterns:
                # Mypy type narrowing: pattern_info["pattern"] is re.Pattern at runtime
                if pattern_info["pattern"].search(line):  # type: ignore[attr-defined]
                    if is_line_suppressed(line, "CWE-22"):
                        suppressed.append(f"CWE-22 suppressed at {file_path}:{line_num}")
                    else:
                        vulnerabilities.append(
                            Vulnerability(
                                cwe="CWE-22",
                                title="Path Traversal Vulnerability",
                                file=file_path,
                                line=line_num,
                                code=line.strip()[:200],
                                pattern=str(pattern_info["description"]),
                                severity=str(pattern_info["severity"]),
                                recommendation=str(pattern_info["recommendation"]),
                            )
                        )
                    break  # One match per pattern category per line

        # Check CWE-78 patterns
        if cwe_filter is None or 78 in cwe_filter:
            for pattern_info in cwe78_patterns:
                # Mypy type narrowing: pattern_info["pattern"] is re.Pattern at runtime
                if pattern_info["pattern"].search(line):  # type: ignore[attr-defined]
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
        title = "Path Traversal" if cwe == "CWE-22" else "Command Injection"
        output.append(f"  {cwe} ({title}): {count}")

    if result.suppressed:
        output.append(f"Suppressed findings: {len(result.suppressed)}")

    output.append("")
    output.append(f"Exit code: {EXIT_VULNERABILITIES} (vulnerabilities detected)")

    return "\n".join(output)


def format_json_output(result: ScanResult) -> str:
    """Format scan result as JSON."""
    output = {
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
        "summary": {
            "total": len(result.vulnerabilities),
            "by_cwe": {},
            "by_severity": {},
        },
        "exit_code": EXIT_VULNERABILITIES if result.vulnerabilities else EXIT_SUCCESS,
    }

    # Mypy type narrowing: output is dict[str, Any] at runtime
    summary = output["summary"]  # type: ignore[index]
    by_cwe = summary["by_cwe"]  # type: ignore[index]
    by_severity = summary["by_severity"]  # type: ignore[index]
    for vuln in result.vulnerabilities:
        by_cwe[vuln.cwe] = by_cwe.get(vuln.cwe, 0) + 1
        by_severity[vuln.severity] = by_severity.get(vuln.severity, 0) + 1

    return json.dumps(output, indent=2)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scan code for CWE-22 and CWE-78 vulnerabilities"
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
        help="Filter by CWE number (22 or 78). Can be specified multiple times.",
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

    # Validate input paths to prevent path traversal (CWE-22)
    try:
        allowed_base = os.path.abspath(".")

        # Validate --directory if provided
        if args.directory:
            directory_path = os.path.abspath(args.directory)
            if not directory_path.startswith(allowed_base):
                raise ValueError(
                    f"Path traversal attempt detected in --directory: "
                    f"{args.directory}"
                )

        # Validate --output if provided
        if args.output:
            output_path = os.path.abspath(args.output)
            if not output_path.startswith(allowed_base):
                raise ValueError(
                    f"Path traversal attempt detected in --output: "
                    f"{args.output}"
                )

        # Validate positional files
        if args.files:
            for file in args.files:
                file_path = os.path.abspath(file)
                if not file_path.startswith(allowed_base):
                    raise ValueError(
                        f"Path traversal attempt detected in file: {file}"
                    )
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
