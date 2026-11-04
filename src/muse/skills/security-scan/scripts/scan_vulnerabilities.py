#!/usr/bin/env python3
# taste-lint: ignore file-size -- pre-existing debt, unlinted before the ADR-119 source classification
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
    0  - No vulnerabilities found, or nothing assessed (files_scanned is 0)
    1  - Scan error (file not found, unsupported --cwe, rejected path)
    2  - Invalid command-line arguments
    3  - Git could not enumerate staged files
    10 - Vulnerabilities detected

With --format json, stdout carries exactly one JSON envelope on every exit and
stderr stays empty. Errors are reported in the envelope's `errors` list.

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
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, NoReturn, cast

# Sibling helpers must import when this file is loaded by path in tests.
# Keep any sys.path change scoped to this import block.
_SCRIPT_DIR = str(Path(__file__).resolve().parent)
_added_to_path = False
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
    _added_to_path = True

try:
    from scan_constants import (
        EXIT_ERROR,
        EXIT_EXTERNAL,
        EXIT_SUCCESS,
        EXIT_USAGE,
        EXIT_VULNERABILITIES,
    )
    from scan_format import format_console_output
    from scan_patterns import CWE78_PATTERNS, scrub_bash_line, scrub_bash_lines
finally:
    if _added_to_path:
        sys.path.remove(_SCRIPT_DIR)

# Re-export the sibling-module symbols so existing callers and tests that read
# `scan_vulnerabilities.CWE78_PATTERNS`, `.format_console_output`, and the exit
# codes keep working after the extraction (issue #1848). Exit codes are
# ADR-035 compliant; their single source of truth is `scan_constants.py`.
__all__ = [
    "CWE78_PATTERNS",
    "EXIT_ERROR",
    "EXIT_EXTERNAL",
    "EXIT_SUCCESS",
    "EXIT_VULNERABILITIES",
    "format_console_output",
    "format_json_output",
    "get_language",
    "is_line_suppressed",
    "main",
    "scan_file",
    "scrub_bash_line",
    "scrub_bash_lines",
]

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

    scan_timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    files_scanned: int = 0
    vulnerabilities: list[Any] = field(default_factory=list)
    suppressed: list[Any] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Set when a failure has its own exit code, such as a git failure.
    exit_code: int | None = None


class GitEnumerationError(RuntimeError):
    """Raised when staged-file enumeration cannot be trusted."""


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
    if ext in language_map:
        return language_map[ext]
    if ext:
        return None
    return _get_shebang_language(file_path)


def _get_shebang_language(file_path: str) -> str | None:
    """Detect supported extensionless scripts from their shebang."""
    try:
        with open(file_path, encoding="utf-8") as f:
            first_line = f.readline().strip().lower()
    except (OSError, UnicodeDecodeError):
        return None
    if not first_line.startswith("#!"):
        return None
    shell_names = {"bash", "dash", "ksh", "sh"}
    command = first_line[2:].strip().split()
    if not command:
        return None
    executable = Path(command[0]).name
    if executable == "env":
        for arg in command[1:]:
            if not arg.startswith("-"):
                executable = Path(arg).name
                break
    if executable in shell_names:
        return "bash"
    return None


_STAGED_FILES_COMMAND = ("git", "diff", "--staged", "--name-only", "--diff-filter=d")


def get_staged_files() -> list[str]:
    """Get list of staged files from git, excluding staged deletions.

    A staged deletion removes the file, so it cannot introduce command
    injection, and reading the missing path in ``scan_file`` would fail.
    ``--diff-filter=d`` drops deletions; unreadable surviving files still
    reach ``scan_file`` and still report an error.

    Note: Uses subprocess with fixed arguments (no user input) - safe from injection.
    """
    try:
        # Safe: fixed command with no user input
        result = subprocess.run(
            list(_STAGED_FILES_COMMAND),
            capture_output=True,
            text=True,
            check=True,
        )
        return [f for f in result.stdout.strip().split("\n") if f]
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise GitEnumerationError(f"{' '.join(_STAGED_FILES_COMMAND)} failed: {detail}") from exc
    except FileNotFoundError as exc:
        raise GitEnumerationError("git executable not found") from exc


def get_directory_files(directory: str) -> list[str]:
    """Get all scannable files from a directory."""
    supported_extensions = {".py", ".ps1", ".psm1", ".sh", ".bash", ".cs"}
    pruned_directories = {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "node_modules",
    }
    files = []
    for root, dirnames, filenames in os.walk(directory):
        dirnames[:] = [name for name in dirnames if name.lower() not in pruned_directories]
        for filename in filenames:
            file_path = os.path.join(root, filename)
            suffix = Path(filename).suffix.lower()
            if suffix in supported_extensions or get_language(file_path) is not None:
                files.append(file_path)
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

    # A pattern with a "scrub_lines" hook matches against the file scrubbed once,
    # so quote and here-document state carries across lines (issue #6624).
    scrubbed: dict[int, list[str]] = {}
    for pattern_info in cwe78_patterns if cwe_filter is None or 78 in cwe_filter else []:
        scrub_lines = cast(
            Callable[[Sequence[str]], list[str]] | None, pattern_info.get("scrub_lines")
        )
        if scrub_lines is not None:
            scrubbed[id(pattern_info)] = scrub_lines(lines)

    for line_num, line in enumerate(lines, 1):
        # Check CWE-78 patterns
        if cwe_filter is None or 78 in cwe_filter:
            for pattern_info in cwe78_patterns:
                pattern = cast(re.Pattern[str], pattern_info["pattern"])
                prepared = scrubbed.get(id(pattern_info))
                if pattern.search(prepared[line_num - 1] if prepared else line):
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


_JSON_SCHEMA_VERSION = 2


def format_json_output(result: ScanResult) -> str:
    """Format scan result as JSON.

    The output envelope carries `schema_version` so downstream consumers can
    detect schema evolution. Readers MUST tolerate unknown fields and treat
    the absence of `schema_version` as v1 (pre-CWE-22-delegation, no
    `summary.delegated_cwes` field). v2 added `summary.delegated_cwes` when
    CWE-22 detection moved to CodeQL (PR #1851, see
    `.project-toolkit/architecture/ADR-054-local-security-scanning.md` amendment).
    """
    by_cwe: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for vuln in result.vulnerabilities:
        by_cwe[vuln.cwe] = by_cwe.get(vuln.cwe, 0) + 1
        by_severity[vuln.severity] = by_severity.get(vuln.severity, 0) + 1

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
        "summary": {
            "total": len(result.vulnerabilities),
            "by_cwe": by_cwe,
            "by_severity": by_severity,
            # Delegated CWE classes: this scanner does not detect them; the named
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
        },
        "exit_code": _exit_code_for_result(result),
    }

    return json.dumps(output, indent=2)


def _exit_code_for_result(result: ScanResult) -> int:
    """Return the public CLI exit code for the aggregate scan result."""
    if result.exit_code is not None:
        return result.exit_code
    if result.errors:
        return EXIT_ERROR
    if result.vulnerabilities:
        return EXIT_VULNERABILITIES
    return EXIT_SUCCESS


def _json_requested(argv: list[str]) -> bool:
    """Return True when argv selects JSON, even if full parsing would fail.

    Argument errors stop argparse before a namespace exists, so this reads the
    format directly. It accepts every spelling argparse does. The last valid
    value wins, so an invalid value after json still reports as JSON.
    """
    selected = None
    for index, arg in enumerate(argv):
        if arg == "--":
            break
        name, has_value, value = arg.partition("=")
        if len(name) > 2 and "--format".startswith(name):
            pass
        elif arg.startswith("-f"):
            has_value, value = len(arg) > 2, arg[2:].removeprefix("=")
        else:
            continue
        if not has_value:
            value = argv[index + 1] if index + 1 < len(argv) else None
        if value in ("console", "json"):
            selected = value
    return selected == "json"


class _JsonAwareParser(argparse.ArgumentParser):
    """Argument parser that keeps its own output JSON when JSON is requested."""

    def error(self, message: str) -> NoReturn:
        """Report an argument error, as an envelope in JSON mode."""
        if _json_requested(sys.argv[1:]):
            print(format_json_output(ScanResult(errors=[message], exit_code=EXIT_USAGE)))
            self.exit(EXIT_USAGE)
        super().error(message)

    def print_help(self, file: IO[str] | None = None) -> None:
        """Print help, inside the envelope in JSON mode."""
        if _json_requested(sys.argv[1:]):
            payload = json.loads(format_json_output(ScanResult()))
            payload["help"] = self.format_help()
            print(json.dumps(payload, indent=2))
            return
        super().print_help(file)


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = _JsonAwareParser(
        description="Scan code for CWE-78 (command injection). CWE-22 path-traversal "
        "detection is delegated to CodeQL in CI; see module docstring.",
        epilog=(
            "Exit codes:\n"
            "  0  no vulnerabilities found\n"
            "  1  scan error (unsupported --cwe, file not found, path traversal)\n"
            "  2  invalid command-line arguments\n"
            "  3  git could not enumerate staged files\n"
            "  10 vulnerabilities detected (CI-blocking)\n"
            "\n"
            "See .project-toolkit/architecture/ADR-054-local-security-scanning.md."
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
        help="Output format. With json, stdout is always one JSON envelope.",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file (default: stdout)",
    )
    return parser


def _emit_json(result: ScanResult, output_path: str | None = None) -> None:
    """Print the one JSON envelope for this run, and write it to a file if asked.

    Pass `output_path` only after path validation. A write failure is reported
    in the printed envelope.
    """
    if output_path:
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(format_json_output(result))
        except OSError as exc:
            result.errors.append(f"Error writing {output_path}: {exc}")
    print(format_json_output(result))


def _exit_with_error(
    args: argparse.Namespace,
    message: str,
    exit_code: int = EXIT_ERROR,
    output_path: str | None = None,
) -> NoReturn:
    """Report a failure on the channel the format requires, then exit."""
    if args.format == "json":
        _emit_json(ScanResult(errors=[message], exit_code=exit_code), output_path)
    else:
        print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(exit_code)


def _validate_cwe_filter(args: argparse.Namespace) -> None:
    """Validate requested CWE filters and warn for delegated coverage."""
    cwe_filter = args.cwe
    supported_cwes = {78}
    delegated_cwes = {22}
    if cwe_filter:
        unsupported = set(cwe_filter) - supported_cwes - delegated_cwes
        if unsupported:
            _exit_with_error(
                args,
                f"--cwe {sorted(unsupported)} not supported by this "
                f"scanner. Supported: {sorted(supported_cwes)} "
                f"(delegated to other tools: {sorted(delegated_cwes)}).",
            )
        # JSON callers read this from `summary.delegated_cwes` instead.
        if 22 in cwe_filter and args.format != "json":
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


def _validate_path(raw: str, label: str, allowed_base: Path) -> None:
    """Reject paths outside the current working directory."""
    candidate = Path(raw).resolve(strict=False)
    if not candidate.is_relative_to(allowed_base):
        raise ValueError(f"Path traversal attempt detected in {label}: {raw}")


def _validate_input_paths(args: argparse.Namespace) -> None:
    """Validate CLI paths before scanning or writing output."""
    try:
        allowed_base = Path(".").resolve(strict=False)
        if args.directory:
            _validate_path(args.directory, "--directory", allowed_base)
        if args.output:
            _validate_path(args.output, "--output", allowed_base)
        if args.files:
            for file in args.files:
                _validate_path(file, "file", allowed_base)
    except ValueError as e:
        _exit_with_error(args, str(e))


def _exit_without_scan(
    args: argparse.Namespace, console_message: str, *, is_error: bool = False
) -> NoReturn:
    """Exit for a request that assessed no files.

    JSON callers get the standard envelope with `files_scanned: 0`, which means
    nothing was assessed. It is not evidence that a file is free of findings.
    A usage error also carries the message in `errors` and exits EXIT_ERROR.
    """
    result = ScanResult(errors=[console_message] if is_error else [])
    if args.format == "json":
        _emit_json(result, args.output)
    else:
        print(console_message)
    sys.exit(_exit_code_for_result(result))


def _collect_files_to_scan(args: argparse.Namespace) -> list[str]:
    """Collect explicit, staged, and directory files from CLI arguments."""
    files_to_scan = []

    if args.git_staged:
        try:
            files_to_scan.extend(get_staged_files())
        except GitEnumerationError as exc:
            # Git failed to enumerate staged files. Fail closed with an external
            # dependency exit code (ADR-035: 3) so callers do not mistake a git
            # failure for a clean scan.
            _exit_with_error(args, str(exc), EXIT_EXTERNAL, args.output)

    if args.directory:
        if not Path(args.directory).is_dir():
            # A missing or non-directory --directory is a mis-specified scan root,
            # not an empty result. Fail closed (EXIT_ERROR) so a typo is never
            # silently treated as a clean scan (os.walk on a missing path yields
            # nothing, which would otherwise look like "no files, all clean").
            _exit_with_error(
                args,
                f"--directory not found or not a directory: {args.directory}",
                output_path=args.output,
            )
        files_to_scan.extend(get_directory_files(args.directory))

    if args.files:
        files_to_scan.extend(args.files)

    if not files_to_scan:
        # A successful --git-staged enumeration with nothing staged exits success
        # with zero coverage. Restrict that to the staged-only case: an explicit
        # --directory or --files target that yielded nothing is a mis-specified
        # request, not a clean scan, so it keeps the usage-error exit (EXIT_ERROR).
        if args.git_staged and not args.directory and not args.files:
            _exit_without_scan(args, "No files to scan (nothing staged, or only deletions staged).")
        _exit_without_scan(
            args,
            "No files to scan. Use --git-staged, --directory, or specify files.",
            is_error=True,
        )

    return list(set(files_to_scan))


def _filter_supported_files(files_to_scan: list[str], args: argparse.Namespace) -> list[str]:
    """Keep files whose extension or shebang maps to a scanner language."""
    supported_files = [f for f in files_to_scan if get_language(f) is not None]

    if not supported_files:
        _exit_without_scan(args, "No supported files found (Python, PowerShell, Bash, C#).")
    return supported_files


def _scan_supported_files(supported_files: list[str], cwe_filter: list[int] | None) -> ScanResult:
    """Scan supported files and aggregate findings."""
    result = ScanResult()
    result.files_scanned = len(supported_files)

    for file_path in supported_files:
        vulns, messages = scan_file(file_path, cwe_filter)
        result.vulnerabilities.extend(vulns)
        for message in messages:
            if message.startswith("Error reading "):
                result.errors.append(message)
            else:
                result.suppressed.append(message)
    return result


def _format_console(result: ScanResult, cwe_filter: list[int] | None) -> str:
    """Format scan results for console or text file output."""
    output = format_console_output(result)
    # Surface CWE-22 delegation in console output too. The JSON envelope
    # carries `summary.delegated_cwes`, but a console caller running
    # `--cwe 22` should see the delegation in stdout, not just stderr.
    if cwe_filter and 22 in cwe_filter:
        output += "\n\nCWE-22: delegated to CodeQL (see .github/workflows/codeql-analysis.yml)"
    return output


def _write_or_print_output(output: str, output_path: str | None) -> None:
    """Write output to a requested file or print to stdout."""
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Results written to {output_path}")
    else:
        print(output)


def _run(args: argparse.Namespace) -> NoReturn:
    """Validate the request, scan, report, and exit."""
    _validate_cwe_filter(args)
    _validate_input_paths(args)
    files_to_scan = _collect_files_to_scan(args)
    supported_files = _filter_supported_files(files_to_scan, args)
    result = _scan_supported_files(supported_files, args.cwe)
    if args.format == "json":
        _emit_json(result, args.output)
    else:
        _write_or_print_output(_format_console(result, args.cwe), args.output)
    sys.exit(_exit_code_for_result(result))


def main() -> None:
    """Main entry point."""
    parser = _build_parser()
    args = parser.parse_args()
    try:
        _run(args)
    except Exception as exc:
        # JSON callers parse stdout, so a crash must not become a traceback.
        if args.format != "json":
            raise
        _exit_with_error(args, f"Unexpected scanner error: {exc}")


if __name__ == "__main__":
    main()
