#!/usr/bin/env python3
"""Validate that documentation files contain no absolute paths.

Scans documentation files for absolute path references that would contaminate
documentation with environment-specific information.

Detects forbidden patterns:
  - Windows absolute paths: C:\\, D:\\, etc.
  - macOS absolute paths: /Users/
  - Linux absolute paths: /home/

EXIT CODES:
  0  - Success: No violations found, or violations found without --fail-on-violation
  1  - Error: Violations found with --fail-on-violation

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ForbiddenPattern:
    """A pattern that should not appear in documentation files."""

    name: str
    pattern: re.Pattern[str]
    description: str
    example: str


@dataclass
class Violation:
    """A single absolute path violation found in a file."""

    file: Path
    line: int
    content: str
    pattern_name: str
    description: str


@dataclass
class ScanResult:
    """Result of scanning files for absolute path violations."""

    files_scanned: int = 0
    violations: list[Violation] = field(default_factory=list)

    @property
    def files_with_violations(self) -> int:
        """Count of unique files with violations."""
        return len({v.file for v in self.violations})


FORBIDDEN_PATTERNS: list[ForbiddenPattern] = [
    ForbiddenPattern(
        name="Windows Absolute Path",
        pattern=re.compile(r"[a-zA-Z]:\\"),
        description="Windows drive letter path (e.g., C:\\, D:\\)",
        example="C:\\Users\\username\\repo\\file.md",
    ),
    ForbiddenPattern(
        name="macOS User Path",
        pattern=re.compile(r"/Users/"),
        description="macOS user home directory path",
        example="/Users/username/repo/file.md",
    ),
    ForbiddenPattern(
        name="Linux Home Path",
        pattern=re.compile(r"/home/"),
        description="Linux user home directory path",
        example="/home/username/repo/file.md",
    ),
]

CODE_FENCE_PATTERN = re.compile(r"^\s*(`{3,}|~{3,})")
INLINE_CODE_PATTERN = re.compile(r"`[^`]+`")


def _should_use_color() -> bool:
    """Determine whether to use ANSI color codes in output."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("CI"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return True


def _color(text: str, code: str, use_color: bool) -> str:
    """Wrap text in ANSI color code if colors are enabled."""
    if not use_color:
        return text
    return f"\033[{code}m{text}\033[0m"


def _red(text: str, use_color: bool) -> str:
    return _color(text, "31", use_color)


def _green(text: str, use_color: bool) -> str:
    return _color(text, "32", use_color)


def _yellow(text: str, use_color: bool) -> str:
    return _color(text, "33", use_color)


def _cyan(text: str, use_color: bool) -> str:
    return _color(text, "36", use_color)


def collect_files(
    root: Path,
    extensions: list[str],
    exclude_paths: list[str],
) -> list[Path]:
    """Collect files matching extensions, excluding specified paths."""
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in extensions:
            continue
        relative = path.relative_to(root).as_posix()
        excluded = False
        for excl in exclude_paths:
            normalized_excl = excl.replace("\\", "/")
            if normalized_excl in relative:
                excluded = True
                break
        if not excluded:
            files.append(path)
    return files


def scan_file(
    filepath: Path,
    patterns: list[ForbiddenPattern],
) -> list[Violation]:
    """Scan a single file for absolute path violations."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except OSError:
        return []

    if not content.strip():
        return []

    violations: list[Violation] = []
    in_code_block = False

    for line_number, line in enumerate(content.splitlines(), start=1):
        if CODE_FENCE_PATTERN.match(line):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            continue

        stripped = INLINE_CODE_PATTERN.sub("", line)

        for pat in patterns:
            if pat.pattern.search(stripped):
                violations.append(
                    Violation(
                        file=filepath,
                        line=line_number,
                        content=line.strip(),
                        pattern_name=pat.name,
                        description=pat.description,
                    )
                )

    return violations


def scan_directory(
    root: Path,
    extensions: list[str],
    exclude_paths: list[str],
    patterns: list[ForbiddenPattern],
) -> ScanResult:
    """Scan all matching files under root for absolute path violations."""
    files = collect_files(root, extensions, exclude_paths)
    result = ScanResult(files_scanned=len(files))

    for filepath in files:
        result.violations.extend(scan_file(filepath, patterns))

    return result


def print_report(result: ScanResult, root: Path, use_color: bool) -> None:
    """Print the violation report to stdout."""
    if not result.violations:
        print(
            _green(
                f"SUCCESS: No absolute paths found in {result.files_scanned} files",
                use_color,
            )
        )
        return

    print(
        _red(
            f"FAILURE: Found {len(result.violations)} absolute path violation(s) "
            f"in {result.files_with_violations} file(s)",
            use_color,
        )
    )
    print()

    violations_by_file: dict[Path, list[Violation]] = {}
    for v in result.violations:
        violations_by_file.setdefault(v.file, []).append(v)

    for filepath, file_violations in violations_by_file.items():
        try:
            relative = filepath.relative_to(root)
        except ValueError:
            relative = filepath
        print(_yellow(f"File: {relative}", use_color))
        print()

        for v in file_violations:
            print(f"  Line {v.line}: {v.pattern_name}")
            print(f"  Pattern: {v.description}")
            print(f"  Content: {_red(v.content, use_color)}")
            print("  Should use relative path instead")
            print()

    print(_cyan("=== Remediation Steps ===", use_color))
    print()
    print("1. Replace absolute paths with relative paths from the document's location")
    print("2. Use forward slashes (/) for cross-platform compatibility")
    print("3. Examples of correct relative paths:")
    print("   - docs/guide.md")
    print("   - ../architecture/design.md")
    print("   - .agents/planning/PRD-feature.md")
    print()


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Validate documentation files contain no absolute paths.",
    )
    parser.add_argument(
        "--path",
        default=".",
        help="Root path to scan (default: current directory)",
    )
    parser.add_argument(
        "--extensions",
        default=".md",
        help="Comma-separated file extensions to scan (default: .md)",
    )
    parser.add_argument(
        "--exclude-paths",
        default=".git,node_modules,.vs,bin,obj,.agents/sessions",
        help="Comma-separated paths to exclude (default: .git,node_modules,...)",
    )
    parser.add_argument(
        "--fail-on-violation",
        action="store_true",
        help="Exit with code 1 if violations found (for CI)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for path normalization validation."""
    parser = build_parser()
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    extensions = [
        ext if ext.startswith(".") else f".{ext}"
        for ext in args.extensions.split(",")
    ]
    exclude_paths = [p.strip() for p in args.exclude_paths.split(",") if p.strip()]
    use_color = _should_use_color()

    print(_cyan("=== Path Normalization Validation ===", use_color))
    print()
    print(f"Scanning path: {root}")
    print(f"Extensions: {', '.join(extensions)}")
    print(f"Excluded paths: {', '.join(exclude_paths)}")
    print()

    result = scan_directory(root, extensions, exclude_paths, FORBIDDEN_PATTERNS)

    if result.files_scanned == 0:
        print(_yellow("No files found to scan.", use_color))
        return 0

    print(f"Files to scan: {result.files_scanned}")
    print()

    print_report(result, root, use_color)

    if result.violations and args.fail_on_violation:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
