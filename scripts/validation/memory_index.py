#!/usr/bin/env python3
"""Validate memory index consistency for tiered memory architecture (ADR-017).

Implements multi-tier validation for the tiered memory index architecture:

P0 (Always Blocking):
- Verifies all domain index entries point to existing files
- Checks keyword density (>=40% unique keywords per skill in domain)
- Validates index format (pure lookup table, no titles/metadata)
- Detects deprecated skill- prefix in index entries
- Detects duplicate entries in same index

P1 (Warning):
- Reports orphaned atomic files not referenced by any index
- Detects unindexed skill- prefixed files

P2 (Warning):
- Minimum keyword count (>=5 per skill)
- Domain prefix naming convention ({domain}-{description})

Exit codes follow ADR-035:
    0 - Success: All P0 validations passed or no memory path found
    1 - Error: P0 validation failures detected (CI mode only)
    2 - Config error (path not found in CI mode)
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class IndexEntry:
    """A parsed entry from a domain index file."""

    keywords: list[str]
    file_name: str
    raw_keywords: str


@dataclass
class DomainIndex:
    """A domain index file with parsed metadata."""

    path: Path
    name: str
    domain: str


@dataclass
class ValidationIssues:
    """Generic validation result with pass/fail and issues."""

    passed: bool = True
    issues: list[str] = field(default_factory=list)


@dataclass
class FileRefResult(ValidationIssues):
    """Result of file reference validation."""

    missing_files: list[str] = field(default_factory=list)
    valid_files: list[str] = field(default_factory=list)
    naming_violations: list[str] = field(default_factory=list)


@dataclass
class KeywordDensityResult(ValidationIssues):
    """Result of keyword density validation."""

    densities: dict[str, float] = field(default_factory=dict)


@dataclass
class DuplicateResult(ValidationIssues):
    """Result of duplicate entry detection."""

    duplicates: list[str] = field(default_factory=list)


@dataclass
class FormatResult(ValidationIssues):
    """Result of index format validation."""

    violation_lines: list[int] = field(default_factory=list)


@dataclass
class MemoryIndexRefResult(ValidationIssues):
    """Result of memory-index reference validation."""

    unreferenced_indices: list[str] = field(default_factory=list)
    broken_references: list[str] = field(default_factory=list)


@dataclass
class Orphan:
    """An orphaned file not referenced by any index."""

    file: str
    domain: str
    expected_index: str


@dataclass
class DomainResult:
    """Full validation result for a single domain index."""

    index_path: str
    entries: int
    file_references: FileRefResult
    keyword_density: KeywordDensityResult
    index_format: FormatResult
    duplicate_entries: DuplicateResult
    minimum_keywords: ValidationIssues
    domain_prefix_naming: ValidationIssues
    passed: bool


@dataclass
class ValidationSummary:
    """Aggregate summary of validation results."""

    total_domains: int = 0
    passed_domains: int = 0
    failed_domains: int = 0
    total_files: int = 0
    missing_files: int = 0
    keyword_issues: int = 0


@dataclass
class ValidationReport:
    """Complete validation report."""

    passed: bool = True
    timestamp: str = ""
    memory_path: str = ""
    domain_results: dict[str, DomainResult] = field(default_factory=dict)
    memory_index_result: MemoryIndexRefResult | None = None
    orphans: list[Orphan] = field(default_factory=list)
    summary: ValidationSummary = field(default_factory=ValidationSummary)


# ---------------------------------------------------------------------------
# Index parsing
# ---------------------------------------------------------------------------

_TABLE_ROW_PATTERN: re.Pattern[str] = re.compile(
    r"^\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|$"
)
_MARKDOWN_LINK_PATTERN: re.Pattern[str] = re.compile(
    r"\[([^\]]+)\]\(([^)]+)\)"
)


def find_domain_indices(memory_path: Path) -> list[DomainIndex]:
    """Find all domain index files (skills-*-index.md pattern)."""
    if not memory_path.exists():
        return []

    indices: list[DomainIndex] = []
    for f in sorted(memory_path.glob("skills-*-index.md")):
        name = f.stem
        # Extract domain: skills-{domain}-index -> {domain}
        domain = re.sub(r"^skills-", "", name)
        domain = re.sub(r"-index$", "", domain)
        indices.append(DomainIndex(path=f, name=name, domain=domain))

    return indices


def parse_index_entries(index_path: Path) -> list[IndexEntry]:
    """Parse a domain index file and extract keyword-file mappings."""
    if not index_path.exists():
        return []

    content = index_path.read_text(encoding="utf-8")
    entries: list[IndexEntry] = []

    for line in content.split("\n"):
        match = _TABLE_ROW_PATTERN.match(line)
        if not match:
            continue

        keywords_str = match.group(1).strip()
        file_name = match.group(2).strip()

        # Skip header and separator rows
        if keywords_str == "Keywords" or re.match(r"^-+$", keywords_str):
            continue
        if re.match(r"^-+$", file_name):
            continue

        # Parse markdown link syntax: [text](filename.md)
        link_match = _MARKDOWN_LINK_PATTERN.search(file_name)
        if link_match:
            link_target = link_match.group(2)
            file_name = re.sub(r"\.md$", "", link_target)

        keyword_list = [kw for kw in keywords_str.split() if kw]

        entries.append(
            IndexEntry(
                keywords=keyword_list,
                file_name=file_name,
                raw_keywords=keywords_str,
            )
        )

    return entries


# ---------------------------------------------------------------------------
# P0 validators
# ---------------------------------------------------------------------------


def check_file_references(
    entries: list[IndexEntry], memory_path: Path
) -> FileRefResult:
    """Validate that all index entries point to existing files.

    Also checks for deprecated 'skill-' prefix (ADR-017 Gap 1/2).
    """
    result = FileRefResult()

    resolved_memory = memory_path.resolve()

    for entry in entries:
        file_path = memory_path / f"{entry.file_name}.md"

        # Security: Prevent path traversal (CWE-22).
        resolved = file_path.resolve()
        if not resolved.is_relative_to(resolved_memory):
            result.passed = False
            result.issues.append(
                f"Path traversal detected: {entry.file_name}.md"
            )
            continue

        # Check for deprecated skill- prefix
        if entry.file_name.startswith("skill-"):
            result.passed = False
            result.naming_violations.append(entry.file_name)
            result.issues.append(
                f"Index references deprecated 'skill-' prefix: "
                f"{entry.file_name}.md (ADR-017 violation)"
            )

        if resolved.exists():
            result.valid_files.append(entry.file_name)
        else:
            result.passed = False
            result.missing_files.append(entry.file_name)
            result.issues.append(f"Missing file: {entry.file_name}.md")

    return result


def check_keyword_density(entries: list[IndexEntry]) -> KeywordDensityResult:
    """Validate that each skill has >=40% unique keywords vs other skills."""
    result = KeywordDensityResult()

    if len(entries) < 2:
        if len(entries) == 1:
            result.densities[entries[0].file_name] = 1.0
        return result

    # Build keyword sets (case-insensitive)
    keyword_sets: dict[str, set[str]] = {}
    for entry in entries:
        keyword_sets[entry.file_name] = {kw.lower() for kw in entry.keywords}

    for entry in entries:
        my_keywords = keyword_sets[entry.file_name]

        # Union of all other entries' keywords
        other_keywords: set[str] = set()
        for other in entries:
            if other.file_name != entry.file_name:
                other_keywords.update(keyword_sets[other.file_name])

        # Count unique keywords
        unique_count = sum(
            1 for kw in my_keywords if kw not in other_keywords
        )

        density = (
            round(unique_count / len(my_keywords), 2)
            if my_keywords
            else 0.0
        )
        result.densities[entry.file_name] = density

        if density < 0.40:
            result.passed = False
            result.issues.append(
                f"Low keyword uniqueness: {entry.file_name} has "
                f"{round(density * 100)}% unique keywords (need >=40%)"
            )

    return result


def check_index_format(index_path: Path) -> FormatResult:
    """Validate that domain index files are pure lookup tables (ADR-017).

    Ensures no titles, metadata blocks, prose, or navigation sections.
    """
    result = FormatResult()

    if not index_path.exists():
        return result

    lines = index_path.read_text(encoding="utf-8").split("\n")
    table_header_found = False

    for line_number, line in enumerate(lines, start=1):
        trimmed = line.strip()

        if not trimmed:
            continue

        # Titles: # ...
        if re.match(r"^#+\s+", trimmed):
            result.passed = False
            result.violation_lines.append(line_number)
            result.issues.append(
                f"Line {line_number}: Title detected - "
                f"'{trimmed}' (prohibited per ADR-017)"
            )
            continue

        # Metadata blocks: **Key**: Value
        if re.match(r"^\*\*[^*]+\*\*:\s*", trimmed):
            result.passed = False
            result.violation_lines.append(line_number)
            result.issues.append(
                f"Line {line_number}: Metadata block detected - "
                f"'{trimmed}' (prohibited per ADR-017)"
            )
            continue

        # Navigation sections: Parent:, > [...]
        if re.match(r"^Parent:\s*", trimmed) or re.match(
            r"^>\s*\[.*\]", trimmed
        ):
            result.passed = False
            result.violation_lines.append(line_number)
            result.issues.append(
                f"Line {line_number}: Navigation section detected - "
                f"'{trimmed}' (prohibited per ADR-017)"
            )
            continue

        # Valid table row
        if re.match(r"^\|.*\|$", trimmed):
            table_header_found = True
            continue

        # Non-table content after table header
        if table_header_found and not re.match(r"^\|.*\|$", trimmed):
            result.passed = False
            result.violation_lines.append(line_number)
            result.issues.append(
                f"Line {line_number}: Non-table content detected - "
                f"'{trimmed}' (prohibited per ADR-017)"
            )

    return result


def check_duplicate_entries(entries: list[IndexEntry]) -> DuplicateResult:
    """Detect duplicate file references within a domain index."""
    result = DuplicateResult()
    seen: set[str] = set()

    for entry in entries:
        if entry.file_name in seen:
            result.passed = False
            if entry.file_name not in result.duplicates:
                result.duplicates.append(entry.file_name)
                result.issues.append(
                    f"Duplicate entry: {entry.file_name} appears "
                    "multiple times in index"
                )
        seen.add(entry.file_name)

    return result


# ---------------------------------------------------------------------------
# P1 validators
# ---------------------------------------------------------------------------


def check_memory_index_references(
    memory_path: Path, domain_indices: list[DomainIndex]
) -> MemoryIndexRefResult:
    """Validate that memory-index references existing domain indices.

    P1 validations:
    1. All domain indices MUST be referenced in memory-index (completeness)
    2. All references in memory-index MUST point to existing files (validity)
    """
    result = MemoryIndexRefResult()
    memory_index_path = memory_path / "memory-index.md"

    if not memory_index_path.exists():
        result.passed = False
        result.issues.append(
            "CRITICAL: memory-index.md not found - "
            "required for tiered architecture"
        )
        return result

    content = memory_index_path.read_text(encoding="utf-8")
    resolved_memory = memory_path.resolve()

    # P1: Check completeness
    for index in domain_indices:
        if index.name not in content:
            result.passed = False
            result.unreferenced_indices.append(index.name)
            result.issues.append(
                f"P1 COMPLETENESS: Domain index not referenced "
                f"in memory-index: {index.name}"
            )

    # P1: Check validity of references
    for line in content.split("\n"):
        match = _TABLE_ROW_PATTERN.match(line)
        if not match:
            continue

        file_entry = match.group(2).strip()

        # Skip header/separator rows
        skip_values = {
            "File", "Essential Memories", "Memory", "Memory Index"
        }
        if file_entry in skip_values or re.match(r"^-+$", file_entry):
            continue

        # Handle comma-separated file lists
        file_names = [
            f.strip() for f in file_entry.split(",") if f.strip()
        ]

        for file_name in file_names:
            # Parse markdown link syntax
            link_match = _MARKDOWN_LINK_PATTERN.search(file_name)
            if link_match:
                link_target = link_match.group(2)
                file_name = re.sub(r"\.md$", "", link_target)

            ref_path = memory_path / f"{file_name}.md"

            # Security: Prevent path traversal (CWE-22).
            resolved_ref = ref_path.resolve()
            if not resolved_ref.is_relative_to(resolved_memory):
                result.passed = False
                result.broken_references.append(file_name)
                result.issues.append(
                    f"P1 VALIDITY: Path traversal detected "
                    f"in memory-index: {file_name}.md"
                )
                continue

            if not resolved_ref.exists():
                result.passed = False
                result.broken_references.append(file_name)
                result.issues.append(
                    f"P1 VALIDITY: memory-index references "
                    f"non-existent file: {file_name}.md"
                )

    return result


def find_orphaned_files(
    all_indices: list[DomainIndex], memory_path: Path
) -> list[Orphan]:
    """Find atomic skill files not referenced by any domain index.

    Detects:
    1. Files matching domain prefix pattern not in any index
    2. Files with deprecated 'skill-' prefix (ADR-017 Gap 4)
    """
    orphans: list[Orphan] = []
    referenced_files: set[str] = set()

    # Collect all referenced files from all indices
    for index in all_indices:
        entries = parse_index_entries(index.path)
        for entry in entries:
            referenced_files.add(entry.file_name)

    # Check for orphaned files
    for f in sorted(memory_path.glob("*.md")):
        base_name = f.stem

        # Skip index files and memory-index
        if base_name.endswith("-index") or base_name == "memory-index":
            continue

        # ADR-017 Gap 4: deprecated skill- prefix
        if (
            base_name.startswith("skill-")
            and base_name not in referenced_files
        ):
            orphans.append(
                Orphan(
                    file=base_name,
                    domain="INVALID",
                    expected_index=(
                        "Rename to {domain}-{description} "
                        "format per ADR-017"
                    ),
                )
            )
            continue

        # Invalid skills-* files (not proper index files)
        if (
            base_name.startswith("skills-")
            and not base_name.endswith("-index")
        ):
            orphans.append(
                Orphan(
                    file=base_name,
                    domain="INVALID",
                    expected_index=(
                        "Rename to {domain}-{description}-index format "
                        "or move to atomic file per ADR-017"
                    ),
                )
            )
            continue

        # Check if file follows atomic naming pattern (domain prefix)
        for index in all_indices:
            if (
                base_name.startswith(f"{index.domain}-")
                and base_name not in referenced_files
            ):
                orphans.append(
                    Orphan(
                        file=base_name,
                        domain=index.domain,
                        expected_index=f"skills-{index.domain}-index",
                    )
                )

    return orphans


# ---------------------------------------------------------------------------
# P2 validators
# ---------------------------------------------------------------------------


def check_minimum_keywords(
    entries: list[IndexEntry], min_keywords: int = 5
) -> ValidationIssues:
    """Validate minimum keyword count (>=5 per skill)."""
    result = ValidationIssues()

    for entry in entries:
        count = len(entry.keywords)
        if count < min_keywords:
            result.passed = False
            result.issues.append(
                f"Insufficient keywords: {entry.file_name} has "
                f"{count} keywords (need >={min_keywords})"
            )

    return result


def check_domain_prefix_naming(
    entries: list[IndexEntry], domain: str
) -> ValidationIssues:
    """Validate that file references follow {domain}-{description} naming."""
    result = ValidationIssues()
    expected_prefix = f"{domain}-"

    for entry in entries:
        if not entry.file_name.startswith(expected_prefix):
            result.passed = False
            result.issues.append(
                f"Naming violation: {entry.file_name} should start "
                f"with '{expected_prefix}' per ADR-017"
            )

    return result


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------


def run_validation(memory_path: Path, output_format: str) -> ValidationReport:
    """Run full memory index validation."""
    from datetime import UTC, datetime

    report = ValidationReport(
        timestamp=datetime.now(UTC).isoformat(),
        memory_path=str(memory_path),
    )

    domain_indices = find_domain_indices(memory_path)
    report.summary.total_domains = len(domain_indices)

    if output_format == "console":
        print(f"Found {len(domain_indices)} domain index(es)")

    for index in domain_indices:
        if output_format == "console":
            print(f"\nValidating: {index.name}")

        entries = parse_index_entries(index.path)

        if output_format == "console":
            print(f"  Entries: {len(entries)}")

        # P0 validations
        file_result = check_file_references(entries, memory_path)
        report.summary.total_files += len(entries)
        report.summary.missing_files += len(file_result.missing_files)

        keyword_result = check_keyword_density(entries)
        if not keyword_result.passed:
            report.summary.keyword_issues += len(keyword_result.issues)

        format_result = check_index_format(index.path)
        duplicate_result = check_duplicate_entries(entries)

        # P2 validations
        min_kw_result = check_minimum_keywords(entries, min_keywords=5)
        prefix_result = check_domain_prefix_naming(entries, index.domain)

        # P0 determines domain pass/fail
        p0_passed = (
            file_result.passed
            and keyword_result.passed
            and format_result.passed
            and duplicate_result.passed
        )

        domain_result = DomainResult(
            index_path=str(index.path),
            entries=len(entries),
            file_references=file_result,
            keyword_density=keyword_result,
            index_format=format_result,
            duplicate_entries=duplicate_result,
            minimum_keywords=min_kw_result,
            domain_prefix_naming=prefix_result,
            passed=p0_passed,
        )
        report.domain_results[index.domain] = domain_result

        if p0_passed:
            report.summary.passed_domains += 1
            if output_format == "console":
                print("  Status: PASS")
        else:
            report.summary.failed_domains += 1
            report.passed = False
            if output_format == "console":
                print("  Status: FAIL")
                for issue in file_result.issues:
                    print(f"    - [P0] {issue}")
                for issue in keyword_result.issues:
                    print(f"    - [P0] {issue}")
                for issue in format_result.issues:
                    print(f"    - [P0] {issue}")
                for issue in duplicate_result.issues:
                    print(f"    - [P0] {issue}")

        if output_format == "console":
            # P2 warnings
            for issue in min_kw_result.issues:
                print(f"    - [P2 WARN] {issue}")
            for issue in prefix_result.issues:
                print(f"    - [P2 WARN] {issue}")

            # Keyword densities
            if keyword_result.densities:
                print("  Keyword uniqueness:")
                for file_name, density in keyword_result.densities.items():
                    pct = round(density * 100)
                    print(f"    {file_name}: {pct}%")

    # P1: memory-index references
    memory_index_result = check_memory_index_references(
        memory_path, domain_indices
    )
    report.memory_index_result = memory_index_result

    if not memory_index_result.passed:
        report.passed = False
        if output_format == "console":
            print("\n[P1] Memory-index validation FAILED:")
            for issue in memory_index_result.issues:
                print(f"  - {issue}")
    elif memory_index_result.issues and output_format == "console":
        print("\nMemory-index warnings:")
        for issue in memory_index_result.issues:
            print(f"  - {issue}")

    # Orphan detection
    orphans = find_orphaned_files(domain_indices, memory_path)
    report.orphans = orphans

    if orphans and output_format == "console":
        print("\n[P1 WARN] Orphaned files detected (not indexed):")
        for orphan in orphans:
            print(
                f"  - {orphan.file} (should be in {orphan.expected_index})"
            )

    return report


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_markdown(report: ValidationReport) -> str:
    """Format validation report as markdown."""
    lines: list[str] = [
        "# Memory Index Validation Report",
        "",
        f"**Date**: {report.timestamp[:16].replace('T', ' ')}",
        f"**Status**: {'PASSED' if report.passed else 'FAILED'}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Domain Indices | {report.summary.total_domains} |",
        f"| Passed | {report.summary.passed_domains} |",
        f"| Failed | {report.summary.failed_domains} |",
        f"| Total Files | {report.summary.total_files} |",
        f"| Missing Files | {report.summary.missing_files} |",
        f"| Keyword Issues | {report.summary.keyword_issues} |",
        "",
    ]

    for domain, result in report.domain_results.items():
        lines.append(f"## Domain: {domain}")
        lines.append("")
        lines.append(f"**Status**: {'PASS' if result.passed else 'FAIL'}")
        lines.append("")

        if result.file_references.issues:
            lines.append("### File Issues")
            for issue in result.file_references.issues:
                lines.append(f"- {issue}")
            lines.append("")

        if result.keyword_density.densities:
            lines.append("### Keyword Uniqueness")
            lines.append("")
            lines.append("| File | Uniqueness |")
            lines.append("|------|------------|")
            for file_name, density in result.keyword_density.densities.items():
                pct = round(density * 100)
                status = "OK" if density >= 0.40 else "LOW"
                lines.append(f"| {file_name} | {pct}% ({status}) |")
            lines.append("")

    if report.orphans:
        lines.append("## Orphaned Files")
        lines.append("")
        for orphan in report.orphans:
            lines.append(
                f"- {orphan.file} - add to {orphan.expected_index}"
            )

    return "\n".join(lines)


def format_json(report: ValidationReport) -> str:
    """Format validation report as JSON."""
    data = dataclasses.asdict(report)
    return json.dumps(data, indent=2, default=str)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with env var defaults."""
    parser = argparse.ArgumentParser(
        description="Validate memory index consistency (ADR-017).",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("MEMORY_PATH", ".serena/memories"),
        help=(
            "Base path to memories directory "
            "(env: MEMORY_PATH, default: .serena/memories)"
        ),
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        default=os.environ.get("CI", "").lower() in ("true", "1"),
        help="CI mode: exit non-zero on P0 failures (env: CI)",
    )
    parser.add_argument(
        "--format",
        choices=["console", "markdown", "json"],
        default=os.environ.get("OUTPUT_FORMAT", "console"),
        dest="output_format",
        help="Output format (env: OUTPUT_FORMAT, default: console)",
    )
    parser.add_argument(
        "--fix-orphans",
        action="store_true",
        default=False,
        help="Report orphaned atomic files that should be indexed",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.output_format == "console":
        print("=== Memory Index Validation (ADR-017) ===")
        print(f"Path: {args.path}")
        print()

    # Resolve path
    target = Path(args.path)
    if not target.is_absolute():
        target = Path.cwd() / target

    if not target.exists():
        if args.output_format == "console":
            print(f"Memory path not found: {target}")
        if args.ci:
            return 2  # ADR-035: config error (path not found)
        return 0

    report = run_validation(target, args.output_format)

    # Output results
    if args.output_format == "console":
        print()
        print("=== Summary ===")
        s = report.summary
        print(
            f"Domains: {s.total_domains} total, "
            f"{s.passed_domains} passed, {s.failed_domains} failed"
        )
        print(
            f"Files: {s.total_files} indexed, "
            f"{s.missing_files} missing"
        )
        print(f"Keyword Issues: {s.keyword_issues}")
        print()
        if report.passed:
            print("Result: PASSED")
        else:
            print("Result: FAILED")
    elif args.output_format == "markdown":
        print(format_markdown(report))
    elif args.output_format == "json":
        print(format_json(report))

    if args.ci:
        return 0 if report.passed else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
