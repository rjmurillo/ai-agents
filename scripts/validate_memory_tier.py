#!/usr/bin/env python3
"""Validate memory tier hierarchy per ADR-017.

Checks:
1. All memories referenced in memory-index.md exist on disk
2. Domain indexes follow {domain}-index.md naming convention
3. Cross-references between indexes and atomic files are valid
4. Tier hierarchy is respected (memory-index -> domain-index -> atomic)

EXIT CODES:
  0  - Success: All memory tier validations pass
  1  - Error: Validation failures detected

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Regex for markdown links: [text](path.md) or [text](dir/path.md)
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+\.md)\)")

# Regex for domain index table rows: | keywords | [file](path.md) |
INDEX_TABLE_ROW_RE = re.compile(
    r"^\|[^|]+\|\s*\[([^\]]*)\]\(([^)]+\.md)\)\s*\|$"
)

# Regex for pure lookup table lines (header, separator, or data row)
LOOKUP_TABLE_LINE_RE = re.compile(
    r"^\s*$"  # empty line
    r"|^\| Keywords \| File \|$"  # header
    r"|^\|[-| ]+\|$"  # separator
    r"|^\|.+\|.+\|$"  # data row
)

# Domain index naming pattern: *-index.md (but not memory-index.md)
DOMAIN_INDEX_RE = re.compile(r"^[a-z][\w-]*-index\.md$")


@dataclass
class ValidationResult:
    """Accumulated validation errors and warnings."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


def extract_file_references(content: str) -> list[str]:
    """Extract all .md file references from markdown links."""
    return [match.group(2) for match in MARKDOWN_LINK_RE.finditer(content)]


def validate_references_exist(
    references: list[str], base_dir: Path, source_file: str, result: ValidationResult
) -> None:
    """Check that all referenced files exist on disk."""
    resolved_base = base_dir.resolve()
    for ref in references:
        ref_path = (base_dir / ref).resolve()
        if not ref_path.is_relative_to(resolved_base):
            result.errors.append(
                f"{source_file}: path traversal attempt detected for reference '{ref}'"
            )
            continue
        if not ref_path.exists():
            result.errors.append(
                f"{source_file}: broken reference -> {ref} (file not found)"
            )


def validate_memory_index(memories_dir: Path, result: ValidationResult) -> list[str]:
    """Validate memory-index.md references and return referenced domain indexes."""
    index_path = memories_dir / "memory-index.md"
    if not index_path.exists():
        result.errors.append("memory-index.md not found in memories directory")
        return []

    content = index_path.read_text(encoding="utf-8")
    references = extract_file_references(content)
    validate_references_exist(references, memories_dir, "memory-index.md", result)
    return references


def find_domain_indexes(memories_dir: Path) -> list[Path]:
    """Find all domain index files (excluding memory-index.md)."""
    indexes = []
    for f in sorted(memories_dir.iterdir()):
        if f.is_file() and DOMAIN_INDEX_RE.match(f.name) and f.name != "memory-index.md":
            indexes.append(f)
    return indexes


def validate_domain_index_format(index_path: Path, result: ValidationResult) -> None:
    """Validate that domain index is a pure lookup table per ADR-017."""
    content = index_path.read_text(encoding="utf-8")
    for line_num, line in enumerate(content.splitlines(), start=1):
        if not LOOKUP_TABLE_LINE_RE.match(line):
            result.errors.append(
                f"{index_path.name}:{line_num}: non-table content in domain index "
                f"(ADR-017 requires pure lookup table)"
            )
            break  # One error per file is enough


def validate_domain_index_references(
    index_path: Path, memories_dir: Path, result: ValidationResult
) -> list[str]:
    """Validate references within a domain index file. Return referenced files."""
    content = index_path.read_text(encoding="utf-8")
    references = extract_file_references(content)
    validate_references_exist(
        references, memories_dir, index_path.name, result
    )

    # Check for deprecated skill- prefix in references
    for ref in references:
        ref_name = Path(ref).stem
        if ref_name.startswith("skill-"):
            result.errors.append(
                f"{index_path.name}: deprecated 'skill-' prefix in reference -> {ref} "
                f"(use {{domain}}-{{description}} format per ADR-017)"
            )

    return references


def validate_orphan_indexes(
    memories_dir: Path,
    memory_index_refs: list[str],
    domain_indexes: list[Path],
    result: ValidationResult,
) -> None:
    """Detect domain indexes not referenced by memory-index.md."""
    referenced_names = {Path(ref).name for ref in memory_index_refs}
    for idx in domain_indexes:
        if idx.name not in referenced_names:
            result.warnings.append(
                f"{idx.name}: domain index not referenced in memory-index.md"
            )


def validate_orphan_atomics(
    memories_dir: Path,
    all_indexed_refs: set[str],
    result: ValidationResult,
) -> None:
    """Detect atomic .md files not referenced by any index."""
    # Collect all .md files (recursive, excluding indexes and special files)
    skip_names = {"memory-index.md", "CLAUDE.md", "README.md", ".token-cache.json"}
    all_md_files: list[Path] = []
    for md_file in sorted(memories_dir.rglob("*.md")):
        rel = md_file.relative_to(memories_dir)
        if str(rel).startswith("."):
            continue
        if md_file.name in skip_names:
            continue
        if DOMAIN_INDEX_RE.match(md_file.name):
            continue
        all_md_files.append(md_file)

    for md_file in all_md_files:
        rel_str = str(md_file.relative_to(memories_dir))
        # Normalize path separators
        rel_str_normalized = rel_str.replace("\\", "/")
        if rel_str_normalized not in all_indexed_refs:
            # Check for skill- prefix orphans (higher severity)
            if md_file.stem.startswith("skill-"):
                result.errors.append(
                    f"{rel_str}: orphaned file with deprecated 'skill-' prefix "
                    f"(not referenced by any index)"
                )
            else:
                result.warnings.append(
                    f"{rel_str}: atomic file not referenced by any domain index"
                )


def validate_memory_tier(memories_dir: Path) -> ValidationResult:
    """Run all ADR-017 memory tier validations."""
    result = ValidationResult()

    if not memories_dir.is_dir():
        result.errors.append(f"Memories directory not found: {memories_dir}")
        return result

    # 1. Validate memory-index.md references
    memory_index_refs = validate_memory_index(memories_dir, result)

    # 2. Find and validate domain indexes
    domain_indexes = find_domain_indexes(memories_dir)

    # 3. Check domain indexes are referenced by memory-index.md
    validate_orphan_indexes(memories_dir, memory_index_refs, domain_indexes, result)

    # 4. Validate each domain index format and references
    all_indexed_refs: set[str] = set()
    # Add memory-index references to the set
    all_indexed_refs.update(memory_index_refs)

    for idx in domain_indexes:
        validate_domain_index_format(idx, result)
        refs = validate_domain_index_references(idx, memories_dir, result)
        all_indexed_refs.update(refs)

    # 5. Check for orphaned atomic files
    validate_orphan_atomics(memories_dir, all_indexed_refs, result)

    return result


def main(argv: list[str] | None = None) -> int:
    """Entry point for memory tier validation."""
    parser = argparse.ArgumentParser(
        description="Validate memory tier hierarchy per ADR-017."
    )
    parser.add_argument(
        "--path",
        default=".serena/memories",
        help="Path to memories directory (default: .serena/memories)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode: warnings become errors",
    )
    args = parser.parse_args(argv)

    memories_dir = Path(args.path).resolve()
    result = validate_memory_tier(memories_dir)

    # In CI mode, promote warnings to errors
    if args.ci and result.warnings:
        result.errors.extend(result.warnings)
        result.warnings = []

    # Print results
    for error in result.errors:
        print(f"ERROR: {error}")
    for warning in result.warnings:
        print(f"WARNING: {warning}")

    if result.is_valid:
        error_count = 0
        warning_count = len(result.warnings)
        print(
            f"Memory tier validation passed. "
            f"{warning_count} warning(s)."
        )
        return 0

    error_count = len(result.errors)
    print(f"Memory tier validation failed. {error_count} error(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
