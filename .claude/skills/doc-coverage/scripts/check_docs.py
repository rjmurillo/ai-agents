#!/usr/bin/env python3
"""
Documentation Coverage Scanner

Detects missing documentation in code (XML docs, docstrings, JSDoc)
and project files (CHANGELOG gaps).

Exit Codes:
    0: Coverage meets threshold
    10: Coverage below threshold (gaps detected)
    1: Error (file not found, parse error)

Usage:
    python3 check_docs.py --target .
    python3 check_docs.py --git-staged --min-coverage 80
    python3 check_docs.py src/models/ --format json
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class DocType(Enum):
    SUMMARY = "summary"
    PARAM = "param"
    RETURNS = "returns"
    EXCEPTION = "exception"
    DOCSTRING = "docstring"
    MODULE_DOCSTRING = "module_docstring"
    JSDOC = "jsdoc"
    CHANGELOG = "changelog"


@dataclass
class DocGap:
    """Represents a missing documentation element."""
    file: str
    line: int
    symbol: str
    symbol_type: str  # class, method, function, property
    missing: list[str]
    language: str

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "symbol": self.symbol,
            "type": self.symbol_type,
            "missing": self.missing,
            "language": self.language
        }


@dataclass
class CoverageReport:
    """Documentation coverage report."""
    total_symbols: int = 0
    documented_symbols: int = 0
    gaps: list[DocGap] = field(default_factory=list)
    files_scanned: int = 0
    threshold: int = 80

    @property
    def coverage_percent(self) -> float:
        if self.total_symbols == 0:
            return 100.0
        return (self.documented_symbols / self.total_symbols) * 100

    @property
    def passed(self) -> bool:
        return self.coverage_percent >= self.threshold

    def to_dict(self) -> dict:
        return {
            "coverage_percent": round(self.coverage_percent, 1),
            "threshold": self.threshold,
            "passed": self.passed,
            "total_symbols": self.total_symbols,
            "documented_symbols": self.documented_symbols,
            "files_scanned": self.files_scanned,
            "gaps": [g.to_dict() for g in self.gaps]
        }


@dataclass
class Config:
    """Scanner configuration."""
    min_coverage_percent: int = 80
    check_public_only: bool = True
    check_changelog: bool = True
    exclude_patterns: list[str] = field(default_factory=lambda: [
        "**/tests/**", "**/test_*.py", "**/*.Tests.cs",
        "**/dist/**", "**/node_modules/**", "**/bin/**", "**/obj/**"
    ])
    languages: dict = field(default_factory=lambda: {
        "csharp": {"require_summary": True, "require_param": True, "require_returns": True},
        "python": {"style": "google", "require_module_docstring": True},
        "javascript": {"require_jsdoc": True, "require_param": True}
    })


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from .doccoveragerc.json or use defaults."""
    if config_path is None:
        config_path = Path(".doccoveragerc.json")

    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
                return Config(
                    min_coverage_percent=data.get("min_coverage_percent", 80),
                    check_public_only=data.get("check_public_only", True),
                    check_changelog=data.get("check_changelog", True),
                    exclude_patterns=data.get("exclude_patterns", Config().exclude_patterns),
                    languages=data.get("languages", Config().languages)
                )
        except (json.JSONDecodeError, KeyError):
            pass

    return Config()


def should_exclude(file_path: Path, exclude_patterns: list[str]) -> bool:
    """Check if file should be excluded based on patterns."""
    file_str = str(file_path)
    for pattern in exclude_patterns:
        # Simple glob matching
        pattern_regex = pattern.replace("**", ".*").replace("*", "[^/]*")
        if re.search(pattern_regex, file_str):
            return True
    return False


def get_git_staged_files() -> list[Path]:
    """Get list of staged files from git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True, text=True, check=True
        )
        return [Path(f) for f in result.stdout.strip().split("\n") if f]
    except subprocess.CalledProcessError:
        return []


def scan_csharp_file(file_path: Path, config: Config) -> tuple[int, int, list[DocGap]]:
    """
    Scan C# file for XML documentation.
    Returns (total_symbols, documented_symbols, gaps)
    """
    total = 0
    documented = 0
    gaps = []

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0, 0, []

    lines = content.split("\n")
    lang_config = config.languages.get("csharp", {})

    # Pattern for public members
    public_pattern = re.compile(
        r"^\s*(?:(?:\[.*?\]\s*)*)"  # Attributes
        r"public\s+"
        r"(?:(?:static|virtual|override|abstract|async|sealed|readonly)\s+)*"
        r"(?:class|struct|interface|enum|record|"
        r"(?:[\w<>\[\],\s]+)\s+)"  # Return type
        r"(\w+)"  # Name
        r"(?:\s*[<({\[:]|$)"  # Following chars
    )

    # XML doc pattern
    xml_doc_pattern = re.compile(r"^\s*///")

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check for public member
        match = public_pattern.match(line)
        if match and config.check_public_only:
            symbol_name = match.group(1)
            symbol_type = "class" if "class " in line else (
                "interface" if "interface " in line else (
                    "method" if "(" in line else "property"
                )
            )

            total += 1

            # Check for XML doc above this line
            has_xml_doc = False
            missing = []

            # Look back for XML docs
            j = i - 1
            while j >= 0 and xml_doc_pattern.match(lines[j]):
                has_xml_doc = True
                j -= 1

            if has_xml_doc:
                # Check for required elements
                doc_block = "\n".join(lines[j+1:i])

                if lang_config.get("require_summary", True) and "<summary>" not in doc_block:
                    missing.append("summary")

                if lang_config.get("require_param", True) and "(" in line:
                    # Extract parameters
                    param_match = re.search(r"\(([^)]*)\)", line)
                    if param_match:
                        params = param_match.group(1)
                        if params.strip():
                            for param in params.split(","):
                                param = param.strip()
                                if param:
                                    # Get param name (last word before = or end)
                                    param_name = re.search(r"(\w+)\s*(?:=|$)", param)
                                    if param_name:
                                        name = param_name.group(1)
                                        if f'name="{name}"' not in doc_block:
                                            missing.append(f"param:{name}")

                if lang_config.get("require_returns", True):
                    # Check if method has non-void return
                    if "(" in line and not re.search(r"\bvoid\s+\w+\s*\(", line):
                        if "<returns>" not in doc_block:
                            missing.append("returns")

                if not missing:
                    documented += 1
                else:
                    gaps.append(DocGap(
                        file=str(file_path),
                        line=i + 1,
                        symbol=symbol_name,
                        symbol_type=symbol_type,
                        missing=missing,
                        language="csharp"
                    ))
            else:
                # No XML doc at all
                missing = ["summary"]
                if lang_config.get("require_param", True) and "(" in line:
                    missing.append("param")
                if lang_config.get("require_returns", True) and "(" in line:
                    if not re.search(r"\bvoid\s+\w+\s*\(", line):
                        missing.append("returns")

                gaps.append(DocGap(
                    file=str(file_path),
                    line=i + 1,
                    symbol=symbol_name,
                    symbol_type=symbol_type,
                    missing=missing,
                    language="csharp"
                ))

        i += 1

    return total, documented, gaps


def scan_python_file(file_path: Path, config: Config) -> tuple[int, int, list[DocGap]]:
    """
    Scan Python file for docstrings.
    Returns (total_symbols, documented_symbols, gaps)
    """
    total = 0
    documented = 0
    gaps = []

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0, 0, []

    lines = content.split("\n")
    lang_config = config.languages.get("python", {})

    # Check module docstring
    if lang_config.get("require_module_docstring", True):
        total += 1
        # First non-comment, non-blank line should be docstring
        first_content_line = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                first_content_line = i
                break

        if lines[first_content_line].strip().startswith(('"""', "'''")):
            documented += 1
        else:
            gaps.append(DocGap(
                file=str(file_path),
                line=1,
                symbol=file_path.stem,
                symbol_type="module",
                missing=["module_docstring"],
                language="python"
            ))

    # Pattern for functions and classes
    def_pattern = re.compile(r"^(\s*)(def|class)\s+(\w+)")

    i = 0
    while i < len(lines):
        line = lines[i]
        match = def_pattern.match(line)

        if match:
            def_type = match.group(2)
            name = match.group(3)

            # Skip private if check_public_only
            if config.check_public_only and name.startswith("_"):
                i += 1
                continue

            total += 1
            symbol_type = "class" if def_type == "class" else "function"

            # Check for docstring on next non-blank line
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1

            if j < len(lines):
                next_line = lines[j].strip()
                if next_line.startswith(('"""', "'''")):
                    documented += 1
                else:
                    gaps.append(DocGap(
                        file=str(file_path),
                        line=i + 1,
                        symbol=name,
                        symbol_type=symbol_type,
                        missing=["docstring"],
                        language="python"
                    ))
            else:
                gaps.append(DocGap(
                    file=str(file_path),
                    line=i + 1,
                    symbol=name,
                    symbol_type=symbol_type,
                    missing=["docstring"],
                    language="python"
                ))

        i += 1

    return total, documented, gaps


def scan_javascript_file(file_path: Path, config: Config) -> tuple[int, int, list[DocGap]]:
    """
    Scan JavaScript/TypeScript file for JSDoc.
    Returns (total_symbols, documented_symbols, gaps)
    """
    total = 0
    documented = 0
    gaps = []

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0, 0, []

    lines = content.split("\n")
    lang_config = config.languages.get("javascript", {})

    # Pattern for exported functions and classes
    export_pattern = re.compile(
        r"^(?:export\s+)?"
        r"(?:(?:async|default)\s+)*"
        r"(?:function|class|const|let|var)\s+"
        r"(\w+)"
    )

    # JSDoc pattern
    jsdoc_end_pattern = re.compile(r"\*/\s*$")

    i = 0
    while i < len(lines):
        line = lines[i]
        match = export_pattern.match(line.strip())

        if match:
            name = match.group(1)
            symbol_type = "class" if "class " in line else "function"

            # Skip if not exported and check_public_only
            if config.check_public_only and "export" not in line:
                i += 1
                continue

            total += 1

            # Check for JSDoc above
            has_jsdoc = False
            j = i - 1
            while j >= 0:
                prev_line = lines[j].strip()
                if jsdoc_end_pattern.search(prev_line):
                    has_jsdoc = True
                    break
                if prev_line and not prev_line.startswith("*") and not prev_line.startswith("//"):
                    break
                j -= 1

            if has_jsdoc:
                documented += 1
            else:
                missing = ["jsdoc"]
                if lang_config.get("require_param", True) and "(" in line:
                    missing.append("@param")
                if lang_config.get("require_returns", True):
                    missing.append("@returns")

                gaps.append(DocGap(
                    file=str(file_path),
                    line=i + 1,
                    symbol=name,
                    symbol_type=symbol_type,
                    missing=missing,
                    language="javascript"
                ))

        i += 1

    return total, documented, gaps


def check_changelog(project_root: Path) -> list[DocGap]:
    """Check for CHANGELOG.md gaps."""
    gaps = []
    changelog_path = project_root / "CHANGELOG.md"

    if not changelog_path.exists():
        gaps.append(DocGap(
            file="CHANGELOG.md",
            line=0,
            symbol="CHANGELOG",
            symbol_type="file",
            missing=["file_exists"],
            language="markdown"
        ))
        return gaps

    try:
        content = changelog_path.read_text(encoding="utf-8")

        # Check for Unreleased section
        if "[Unreleased]" not in content and "## Unreleased" not in content:
            gaps.append(DocGap(
                file="CHANGELOG.md",
                line=1,
                symbol="Unreleased",
                symbol_type="section",
                missing=["unreleased_section"],
                language="markdown"
            ))

    except (OSError, UnicodeDecodeError):
        pass

    return gaps


def scan_directory(
    target: Path,
    config: Config,
    git_staged_only: bool = False
) -> CoverageReport:
    """Scan directory for documentation coverage."""
    report = CoverageReport(threshold=config.min_coverage_percent)

    if git_staged_only:
        files = get_git_staged_files()
    else:
        files = list(target.rglob("*"))

    # Filter by language
    language_extensions = {
        ".cs": scan_csharp_file,
        ".py": scan_python_file,
        ".js": scan_javascript_file,
        ".ts": scan_javascript_file,
        ".jsx": scan_javascript_file,
        ".tsx": scan_javascript_file,
    }

    for file_path in files:
        if not file_path.is_file():
            continue

        if should_exclude(file_path, config.exclude_patterns):
            continue

        ext = file_path.suffix.lower()
        scanner = language_extensions.get(ext)

        if scanner:
            report.files_scanned += 1
            total, documented, gaps = scanner(file_path, config)
            report.total_symbols += total
            report.documented_symbols += documented
            report.gaps.extend(gaps)

    # Check CHANGELOG
    if config.check_changelog:
        changelog_gaps = check_changelog(target if target.is_dir() else target.parent)
        report.gaps.extend(changelog_gaps)

    return report


def format_text_report(report: CoverageReport) -> str:
    """Format report as human-readable text."""
    lines = [
        "Documentation Coverage Report",
        "=" * 29,
        "",
        f"Overall Coverage: {report.coverage_percent:.1f}%"
        + (f" (below {report.threshold}% threshold)" if not report.passed else ""),
        f"Files Scanned: {report.files_scanned}",
        f"Symbols: {report.documented_symbols}/{report.total_symbols}",
        "",
    ]

    if report.gaps:
        lines.append(f"Gaps Found: {len(report.gaps)}")
        lines.append("")

        # Group by file
        by_file: dict[str, list[DocGap]] = {}
        for gap in report.gaps:
            if gap.file not in by_file:
                by_file[gap.file] = []
            by_file[gap.file].append(gap)

        for file_path, gaps in by_file.items():
            lines.append(file_path)
            for gap in gaps:
                lines.append(f"  Line {gap.line}: {gap.symbol} ({gap.symbol_type})")
                for missing in gap.missing:
                    lines.append(f"    - Missing: {missing}")
            lines.append("")
    else:
        lines.append("No gaps found! Documentation is complete.")

    return "\n".join(lines)


def format_markdown_report(report: CoverageReport) -> str:
    """Format report as Markdown."""
    status = "✅ PASS" if report.passed else "❌ FAIL"

    lines = [
        "# Documentation Coverage Report",
        "",
        f"**Status**: {status}",
        f"**Coverage**: {report.coverage_percent:.1f}% (threshold: {report.threshold}%)",
        f"**Files Scanned**: {report.files_scanned}",
        f"**Symbols**: {report.documented_symbols}/{report.total_symbols}",
        "",
    ]

    if report.gaps:
        lines.append("## Gaps Found")
        lines.append("")
        lines.append("| File | Line | Symbol | Type | Missing |")
        lines.append("|------|------|--------|------|---------|")

        for gap in report.gaps:
            missing_str = ", ".join(gap.missing)
            lines.append(f"| {gap.file} | {gap.line} | {gap.symbol} | {gap.symbol_type} | {missing_str} |")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Scan code for documentation coverage"
    )
    parser.add_argument(
        "--target", "-t",
        type=Path,
        default=Path("."),
        help="Directory or file to scan"
    )
    parser.add_argument(
        "--git-staged",
        action="store_true",
        help="Only scan git staged files"
    )
    parser.add_argument(
        "--min-coverage",
        type=int,
        default=80,
        help="Minimum coverage percentage (default: 80)"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output file (default: stdout)"
    )
    parser.add_argument(
        "--config", "-c",
        type=Path,
        help="Config file path"
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Specific files to scan"
    )

    args = parser.parse_args()

    # Load config
    config = load_config(args.config)
    config.min_coverage_percent = args.min_coverage

    # Determine what to scan
    if args.files:
        # Scan specific files
        report = CoverageReport(threshold=config.min_coverage_percent)
        for file_path in args.files:
            if file_path.suffix == ".cs":
                total, documented, gaps = scan_csharp_file(file_path, config)
            elif file_path.suffix == ".py":
                total, documented, gaps = scan_python_file(file_path, config)
            elif file_path.suffix in (".js", ".ts", ".jsx", ".tsx"):
                total, documented, gaps = scan_javascript_file(file_path, config)
            else:
                continue
            report.files_scanned += 1
            report.total_symbols += total
            report.documented_symbols += documented
            report.gaps.extend(gaps)
    else:
        # Scan directory
        report = scan_directory(
            args.target,
            config,
            git_staged_only=args.git_staged
        )

    # Format output
    if args.format == "json":
        output = json.dumps(report.to_dict(),
    elif args.format == "markdown":
        output = format_markdown_report(report)
    else:
        output = format_text_report(report)

    # Write output
    if args.output:
        args.output.write_text(output, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(output)

    # Exit code
    if report.passed:
        return 0
    else:
        return 10


if __name__ == "__main__":
    sys.exit(main())
