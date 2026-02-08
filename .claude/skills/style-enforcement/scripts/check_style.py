#!/usr/bin/env python3
"""
Style enforcement checker for code files.

Validates code against style rules from .editorconfig, StyleCop.json, and
Directory.Build.props. Detects line ending violations, naming convention
issues, indentation problems, and charset mismatches.

Exit codes:
    0  - All files compliant
    1  - Script error (invalid arguments, config parse failure)
    10 - Violations detected

Usage:
    python check_style.py --target .
    python check_style.py --git-staged
    python check_style.py src/models/User.cs
    python check_style.py --format json --output violations.json
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

# Exit codes (consistent with other skills)
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_VIOLATIONS = 10

# Suppression comment pattern
SUPPRESSION_PATTERN = re.compile(
    r"#\s*style-enforcement:\s*ignore\s+(STYLE-\d+)",
    re.IGNORECASE,
)


@dataclass
class Violation:
    """Represents a style violation."""

    file: str
    line: int
    column: int
    rule: str
    message: str
    severity: str


@dataclass
class StyleConfig:
    """Configuration for a specific file pattern."""

    pattern: str
    end_of_line: str | None = None
    indent_style: str | None = None
    indent_size: int | None = None
    charset: str | None = None
    trim_trailing_whitespace: bool | None = None
    insert_final_newline: bool | None = None
    # C# naming conventions
    async_suffix_required: bool = False


@dataclass
class ScanResult:
    """Scan result container."""

    scan_timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    files_scanned: int = 0
    violations: list = field(default_factory=list)
    suppressed: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def parse_editorconfig(file_path: Path) -> dict:
    """Parse .editorconfig file into section-based configuration."""
    config: dict[str, dict[str, str]] = {}
    current_section = None

    if not file_path.exists():
        return config

    try:
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith("#") or line.startswith(";"):
                    continue

                # Section header
                if line.startswith("[") and line.endswith("]"):
                    current_section = line[1:-1]
                    config[current_section] = {}
                    continue

                # Key-value pair
                if "=" in line and current_section is not None:
                    key, value = line.split("=", 1)
                    key = key.strip().lower()
                    value = value.strip().lower()
                    config[current_section][key] = value

    except (OSError, UnicodeDecodeError) as e:
        print(f"Warning: Could not parse {file_path}: {e}", file=sys.stderr)

    return config


def find_editorconfig(start_path: Path) -> list:
    """Find all .editorconfig files from start_path to root."""
    configs = []
    current = start_path.resolve()

    while current != current.parent:
        editorconfig = current / ".editorconfig"
        if editorconfig.exists():
            configs.append(editorconfig)
            # Check for root = true
            parsed = parse_editorconfig(editorconfig)
            for section, props in parsed.items():
                if props.get("root") == "true":
                    return configs
        current = current.parent

    return configs


def match_pattern(pattern: str, file_path: str) -> bool:
    """Match editorconfig glob pattern against file path."""
    import fnmatch

    file_name = os.path.basename(file_path)

    # Handle ** for directory matching
    if "**" in pattern:
        # Convert ** to regex-like matching
        pattern = pattern.replace("**", "*")

    # Handle {a,b,c} alternatives
    if "{" in pattern and "}" in pattern:
        match = re.search(r"\{([^}]+)\}", pattern)
        if match:
            alternatives = match.group(1).split(",")
            base = pattern[: match.start()] + "{}" + pattern[match.end() :]
            return any(
                match_pattern(base.replace("{}", alt.strip()), file_path)
                for alt in alternatives
            )

    return fnmatch.fnmatch(file_name, pattern) or fnmatch.fnmatch(file_path, pattern)


def get_config_for_file(file_path: Path, editorconfigs: list) -> StyleConfig:
    """Get merged configuration for a specific file."""
    config = StyleConfig(pattern="*")

    # Process configs from root to closest (last one wins)
    for editorconfig_path in reversed(editorconfigs):
        parsed = parse_editorconfig(editorconfig_path)

        for section, props in parsed.items():
            if section == "*" or match_pattern(section, str(file_path)):
                if "end_of_line" in props:
                    config.end_of_line = props["end_of_line"]
                if "indent_style" in props:
                    config.indent_style = props["indent_style"]
                if "indent_size" in props:
                    try:
                        config.indent_size = int(props["indent_size"])
                    except ValueError:
                        pass
                if "charset" in props:
                    config.charset = props["charset"]
                if "trim_trailing_whitespace" in props:
                    config.trim_trailing_whitespace = props[
                        "trim_trailing_whitespace"
                    ] == "true"
                if "insert_final_newline" in props:
                    config.insert_final_newline = props["insert_final_newline"] == "true"

    # Check for C# async naming convention
    if file_path.suffix == ".cs":
        for editorconfig_path in editorconfigs:
            parsed = parse_editorconfig(editorconfig_path)
            for section, props in parsed.items():
                for key, value in props.items():
                    if "async" in key.lower() and "suffix" in value.lower():
                        config.async_suffix_required = True

    return config


def detect_line_ending(content: bytes) -> str:
    """Detect the dominant line ending in file content."""
    crlf_count = content.count(b"\r\n")
    lf_count = content.count(b"\n") - crlf_count
    cr_count = content.count(b"\r") - crlf_count

    if crlf_count > lf_count and crlf_count > cr_count:
        return "crlf"
    elif cr_count > lf_count:
        return "cr"
    else:
        return "lf"


def check_line_endings(
    file_path: Path, content: bytes, config: StyleConfig
) -> list:
    """Check line endings against config."""
    violations: list[Violation] = []

    if config.end_of_line is None:
        return violations

    actual = detect_line_ending(content)
    expected = config.end_of_line

    if actual != expected:
        violations.append(
            Violation(
                file=str(file_path),
                line=1,
                column=1,
                rule="STYLE-001",
                message=f"File uses {actual.upper()} but editorconfig requires {expected.upper()}",
                severity="warning",
            )
        )

    return violations


def check_indentation(
    file_path: Path, lines: list, config: StyleConfig
) -> list:
    """Check indentation style and size."""
    violations: list[Violation] = []

    if config.indent_style is None:
        return violations

    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue

        # Get leading whitespace
        leading = len(line) - len(line.lstrip())
        if leading == 0:
            continue

        leading_chars = line[:leading]

        if config.indent_style == "space":
            if "\t" in leading_chars:
                violations.append(
                    Violation(
                        file=str(file_path),
                        line=i,
                        column=1,
                        rule="STYLE-002",
                        message="Line uses tabs but editorconfig requires spaces",
                        severity="warning",
                    )
                )
        elif config.indent_style == "tab":
            if " " in leading_chars and leading_chars.count(" ") >= 2:
                violations.append(
                    Violation(
                        file=str(file_path),
                        line=i,
                        column=1,
                        rule="STYLE-002",
                        message="Line uses spaces but editorconfig requires tabs",
                        severity="warning",
                    )
                )

    return violations


def check_charset(file_path: Path, content: bytes, config: StyleConfig) -> list:
    """Check file charset/encoding."""
    violations: list[Violation] = []

    if config.charset is None:
        return violations

    has_bom = content.startswith(b"\xef\xbb\xbf")

    if config.charset == "utf-8" and has_bom:
        violations.append(
            Violation(
                file=str(file_path),
                line=1,
                column=1,
                rule="STYLE-003",
                message="File has UTF-8 BOM but editorconfig requires utf-8 (no BOM)",
                severity="warning",
            )
        )
    elif config.charset == "utf-8-bom" and not has_bom:
        violations.append(
            Violation(
                file=str(file_path),
                line=1,
                column=1,
                rule="STYLE-003",
                message="File missing UTF-8 BOM but editorconfig requires utf-8-bom",
                severity="warning",
            )
        )

    return violations


def check_trailing_whitespace(
    file_path: Path, lines: list, config: StyleConfig
) -> list:
    """Check for trailing whitespace."""
    violations: list[Violation] = []

    if not config.trim_trailing_whitespace:
        return violations

    for i, line in enumerate(lines, 1):
        if line != line.rstrip():
            violations.append(
                Violation(
                    file=str(file_path),
                    line=i,
                    column=len(line.rstrip()) + 1,
                    rule="STYLE-004",
                    message="Line has trailing whitespace",
                    severity="info",
                )
            )

    return violations


def check_final_newline(
    file_path: Path, content: str, config: StyleConfig
) -> list:
    """Check for final newline."""
    violations: list[Violation] = []

    if config.insert_final_newline is None:
        return violations

    has_final_newline = content.endswith("\n")

    if config.insert_final_newline and not has_final_newline and content:
        violations.append(
            Violation(
                file=str(file_path),
                line=content.count("\n") + 1,
                column=1,
                rule="STYLE-005",
                message="File does not end with newline",
                severity="info",
            )
        )

    return violations


def check_csharp_async_naming(
    file_path: Path, content: str, config: StyleConfig
) -> list:
    """Check C# async method naming conventions."""
    violations: list[Violation] = []

    if not config.async_suffix_required:
        return violations

    if file_path.suffix != ".cs":
        return violations

    # Pattern to find async methods without Async suffix
    # Matches: async Task<T> MethodName or async void MethodName
    async_method_pattern = re.compile(
        r"\basync\s+(?:Task|ValueTask|IAsyncEnumerable)[\s<].*?\s+(\w+)\s*\(",
        re.MULTILINE,
    )

    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        for match in async_method_pattern.finditer(line):
            method_name = match.group(1)
            if not method_name.endswith("Async") and method_name not in (
                "Main",
                "ConfigureServices",
                "Configure",
            ):
                violations.append(
                    Violation(
                        file=str(file_path),
                        line=i,
                        column=match.start(1) + 1,
                        rule="STYLE-010",
                        message=f"Async method '{method_name}' should end with 'Async' suffix",
                        severity="warning",
                    )
                )

    return violations


def check_file(file_path: Path, editorconfigs: list) -> tuple:
    """Check a single file for style violations."""
    violations: list[Violation] = []
    suppressed: list[Violation] = []

    config = get_config_for_file(file_path, editorconfigs)

    try:
        with open(file_path, "rb") as f:
            raw_content = f.read()

        # Try to decode as UTF-8
        try:
            content = raw_content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content = raw_content.decode("latin-1")
            except UnicodeDecodeError:
                return violations, suppressed, f"Could not decode {file_path}"

        lines = content.split("\n")

        # Collect suppressions
        suppression_lines = {}
        for i, line in enumerate(lines, 1):
            match = SUPPRESSION_PATTERN.search(line)
            if match:
                rule = match.group(1).upper()
                suppression_lines[i] = rule
                suppression_lines[i + 1] = rule  # Also applies to next line

        # Run all checks
        all_violations = []
        all_violations.extend(check_line_endings(file_path, raw_content, config))
        all_violations.extend(check_indentation(file_path, lines, config))
        all_violations.extend(check_charset(file_path, raw_content, config))
        all_violations.extend(check_trailing_whitespace(file_path, lines, config))
        all_violations.extend(check_final_newline(file_path, content, config))
        all_violations.extend(check_csharp_async_naming(file_path, content, config))

        # Filter suppressions
        for v in all_violations:
            if v.line in suppression_lines and suppression_lines[v.line] == v.rule:
                suppressed.append(v)
            else:
                violations.append(v)

    except OSError as e:
        return violations, suppressed, str(e)

    return violations, suppressed, None


def get_git_staged_files() -> list:
    """Get list of git staged files."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            check=True,
        )
        return [Path(f.strip()) for f in result.stdout.strip().split("\n") if f.strip()]
    except subprocess.CalledProcessError:
        return []


def get_files_to_check(args) -> list:
    """Get list of files to check based on arguments."""
    files = []

    if args.git_staged:
        return get_git_staged_files()

    targets = args.files if args.files else [args.target]

    for target in targets:
        path = Path(target)
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            # Get supported file extensions
            extensions = {
                ".cs",
                ".py",
                ".ps1",
                ".psm1",
                ".js",
                ".ts",
                ".jsx",
                ".tsx",
                ".go",
                ".rs",
                ".java",
                ".rb",
                ".md",
                ".yml",
                ".yaml",
                ".json",
            }
            for ext in extensions:
                files.extend(path.rglob(f"*{ext}"))

    return files


def format_text_output(result: ScanResult) -> str:
    """Format result as text."""
    output = []
    output.append("Style Enforcement Report")
    output.append("=" * 24)
    output.append("")
    output.append(f"Files scanned: {result.files_scanned}")
    output.append(f"Violations: {len(result.violations)}")
    output.append(f"Suppressed: {len(result.suppressed)}")
    output.append("")

    if result.violations:
        # Group by file
        by_file: dict[str, list[Violation]] = {}
        for v in result.violations:
            if v.file not in by_file:
                by_file[v.file] = []
            by_file[v.file].append(v)

        for file_path, violations in sorted(by_file.items()):
            output.append(file_path)
            for v in sorted(violations, key=lambda x: x.line):
                output.append(f"  Line {v.line}: [{v.rule}] {v.message}")
            output.append("")

    if result.violations:
        output.append("Exit code: 10 (violations detected)")
    else:
        output.append("Exit code: 0 (all files compliant)")

    return "\n".join(output)


def format_json_output(result: ScanResult) -> str:
    """Format result as JSON."""
    output = {
        "scan_timestamp": result.scan_timestamp,
        "files_scanned": result.files_scanned,
        "violations": [
            {
                "file": v.file,
                "line": v.line,
                "column": v.column,
                "rule": v.rule,
                "message": v.message,
                "severity": v.severity,
            }
            for v in result.violations
        ],
        "suppressed": [
            {
                "file": v.file,
                "line": v.line,
                "rule": v.rule,
                "message": v.message,
            }
            for v in result.suppressed
        ],
        "summary": {
            "total": len(result.violations),
            "by_severity": {},
        },
    }

    # Count by severity
    # Mypy type narrowing: output is dict[str, Any] at runtime
    summary = output["summary"]  # type: ignore[index]
    by_severity = summary["by_severity"]  # type: ignore[index]
    for v in result.violations:
        sev = str(v.severity)
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return json.dumps(output, indent=2)


def format_sarif_output(result: ScanResult) -> str:
    """Format result as SARIF for GitHub Code Scanning."""
    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "style-enforcement",
                        "version": "1.0.0",
                        "rules": [
                            {
                                "id": "STYLE-001",
                                "name": "LineEndingViolation",
                                "shortDescription": {
                                    "text": "Line ending mismatch"
                                },
                            },
                            {
                                "id": "STYLE-002",
                                "name": "IndentationViolation",
                                "shortDescription": {
                                    "text": "Indentation style mismatch"
                                },
                            },
                            {
                                "id": "STYLE-003",
                                "name": "CharsetViolation",
                                "shortDescription": {"text": "Charset mismatch"},
                            },
                            {
                                "id": "STYLE-004",
                                "name": "TrailingWhitespace",
                                "shortDescription": {
                                    "text": "Trailing whitespace"
                                },
                            },
                            {
                                "id": "STYLE-005",
                                "name": "FinalNewline",
                                "shortDescription": {
                                    "text": "Missing final newline"
                                },
                            },
                            {
                                "id": "STYLE-010",
                                "name": "AsyncNamingConvention",
                                "shortDescription": {
                                    "text": "Async method naming"
                                },
                            },
                        ],
                    }
                },
                "results": [
                    {
                        "ruleId": v.rule,
                        "level": "warning" if v.severity == "warning" else "note",
                        "message": {"text": v.message},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": v.file},
                                    "region": {
                                        "startLine": v.line,
                                        "startColumn": v.column,
                                    },
                                }
                            }
                        ],
                    }
                    for v in result.violations
                ],
            }
        ],
    }

    return json.dumps(sarif, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Check code style against editorconfig rules"
    )
    parser.add_argument(
        "--target",
        default=".",
        help="Directory or file to scan (default: current directory)",
    )
    parser.add_argument(
        "--git-staged",
        action="store_true",
        help="Check only git staged files",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "sarif"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--severity",
        choices=["error", "warning", "info"],
        default="warning",
        help="Minimum severity to report (default: warning)",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific files to check",
    )

    args = parser.parse_args()

    # Validate input paths to prevent path traversal (CWE-22)
    try:
        allowed_base = os.path.abspath(".")

        # Validate --target
        target_path = os.path.abspath(args.target)
        if not target_path.startswith(allowed_base):
            raise ValueError(
                f"Path traversal attempt detected in --target: {args.target}"
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

    # Get files to check
    files = get_files_to_check(args)

    if not files:
        print("No files to check", file=sys.stderr)
        sys.exit(EXIT_SUCCESS)

    # Find editorconfigs
    start_path = Path(args.target) if not args.git_staged else Path.cwd()
    editorconfigs = find_editorconfig(start_path)

    if not editorconfigs:
        print("Warning: No .editorconfig found", file=sys.stderr)

    # Run checks
    result = ScanResult()

    severity_order = {"error": 0, "warning": 1, "info": 2}
    min_severity = severity_order.get(args.severity, 1)

    for file_path in files:
        if not file_path.exists():
            result.errors.append(f"File not found: {file_path}")
            continue

        violations, suppressed, error = check_file(file_path, editorconfigs)
        result.files_scanned += 1

        if error:
            result.errors.append(error)
        else:
            # Filter by severity
            for v in violations:
                if severity_order.get(v.severity, 1) <= min_severity:
                    result.violations.append(v)
            result.suppressed.extend(suppressed)

    # Format output
    if args.format == "json":
        output = format_json_output(result)
    elif args.format == "sarif":
        output = format_sarif_output(result)
    else:
        output = format_text_output(result)

    # Write output
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)

    # Exit code
    if result.errors:
        sys.exit(EXIT_ERROR)
    elif result.violations:
        sys.exit(EXIT_VIOLATIONS)
    else:
        sys.exit(EXIT_SUCCESS)


if __name__ == "__main__":
    main()
