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
import posixpath
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Script entry points need the repository path before shared-module imports.
from scripts.utils.markdown_parser import (  # noqa: E402
    _create_parser,
    _raise_if_nesting_truncated,
)

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
    duplicate_references: list[str] = field(default_factory=list)


@dataclass
class NamingConventionResult(ValidationIssues):
    """Result of naming convention validation."""

    violations: list[str] = field(default_factory=list)


@dataclass
class FrontmatterResult(ValidationIssues):
    """Result of frontmatter YAML validity validation."""

    invalid_files: list[str] = field(default_factory=list)


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
    naming_convention: NamingConventionResult | None = None
    frontmatter_validity: FrontmatterResult | None = None
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
_DOMAIN_INDEX_FILENAME_PATTERN: re.Pattern[str] = re.compile(
    r"^[a-z][\w-]*-index\.md$"
)
_SKILLS_DOMAIN_INDEX_FILENAME_PATTERN: re.Pattern[str] = re.compile(
    r"^skills-.+-index\.md$"
)
_SPECIAL_MEMORY_FILENAMES = frozenset({
    "CLAUDE.md",
    "README.md",
    "memory-index.md",
})
OrphanPolicy = Literal["strict", "ratchet"]
_URL_PERCENT_ESCAPE_PATTERN = re.compile(r"%[0-9A-Fa-f]{2}")
_HTML_TAG_PATTERN = re.compile(
    r"^<\s*(?P<closing>/)?\s*(?P<name>[A-Za-z][A-Za-z0-9:-]*)"
)
_HTML_VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_MARKDOWN_PARSER = _create_parser()


def _resolve_memory_reference(
    memory_path: Path,
    resolved_memory: Path,
    file_name: str,
) -> tuple[str | None, Path, str | None]:
    """Resolve a memory reference and return its canonical identity."""
    normalized_name = file_name.replace("\\", "/")
    reference_path = memory_path / f"{normalized_name}.md"
    current_path = memory_path
    for path_part in Path(f"{normalized_name}.md").parts:
        current_path /= path_part
        if current_path.is_symlink():
            return None, reference_path, "symbolic link"

    resolved_ref = reference_path.resolve()
    if not resolved_ref.is_relative_to(resolved_memory):
        return None, resolved_ref, "Path traversal"

    relative_ref = resolved_ref.relative_to(resolved_memory).as_posix()
    identity = re.sub(r"\.md$", "", relative_ref, flags=re.IGNORECASE)
    canonical_identity = os.path.normcase(identity).replace("\\", "/")
    return canonical_identity, resolved_ref, None


def _invalid_destination_reason(destination: str) -> str | None:
    """Return why a Markdown destination is unsafe to canonicalize."""
    if _URL_PERCENT_ESCAPE_PATTERN.search(destination):
        return "URL percent escape"
    if any(character.isspace() for character in destination):
        return "whitespace"
    if "(" in destination or ")" in destination:
        return "parenthesis"
    if "\\" in destination:
        return "backslash"
    if "?" in destination:
        return "query"
    if "#" in destination:
        return "fragment"
    return None


def _raw_html_depth(content: str, depth: int) -> int:
    """Track whether later inline tokens render inside raw HTML."""
    match = _HTML_TAG_PATTERN.match(content)
    if match is None:
        return depth
    if match.group("closing"):
        return max(depth - 1, 0)
    tag_name = match.group("name").lower()
    if content.rstrip().endswith("/>") or tag_name in _HTML_VOID_ELEMENTS:
        return depth
    return depth + 1


def _extract_memory_reference_names(
    content: str,
) -> tuple[list[str], list[str], list[str]]:
    """Extract references from the CommonMark token stream."""
    issues: list[str] = []
    destinations: list[str] = []
    linked_destinations: list[str] = []
    inside_table = False
    inside_file_cell = False
    table_cell_index = 0
    try:
        tokens = _MARKDOWN_PARSER.parse(content)
        _raise_if_nesting_truncated(
            content,
            tokens,
            _MARKDOWN_PARSER,
        )
    except (RuntimeError, ValueError) as exc:
        return [], [], [f"P1 VALIDITY: Markdown parse failed: {exc}"]

    for token in tokens:
        if token.type == "table_open":
            inside_table = True
        elif token.type == "table_close":
            inside_table = False
        elif token.type == "tr_open":
            table_cell_index = 0
        elif token.type == "td_open":
            inside_file_cell = table_cell_index == 1
            table_cell_index += 1
        elif token.type == "td_close":
            inside_file_cell = False
        elif token.type != "inline":
            continue

        should_collect = not inside_table or inside_file_cell
        if not should_collect:
            continue
        children = token.children or []
        inline_destinations: list[str] = []
        plain_text: list[str] = []
        html_depth = 0
        link_depth = 0
        for child in children:
            if child.type == "html_inline":
                html_depth = _raw_html_depth(child.content, html_depth)
            elif child.type == "link_open":
                link_depth += 1
                href = child.attrGet("href")
                if not isinstance(href, str):
                    issues.append(
                        "P1 VALIDITY: parsed link has no destination"
                    )
                elif html_depth == 0:
                    inline_destinations.append(href)
            elif child.type == "link_close":
                link_depth = max(link_depth - 1, 0)
            elif child.type == "image":
                issues.append(
                    "P1 VALIDITY: memory-index images are unsupported"
                )
            elif child.type == "text" and link_depth == 0:
                plain_text.append(child.content)
                is_section_marker = bool(
                    re.fullmatch(r"\[[^\[\]\n]+\]", child.content.strip())
                )
                if not is_section_marker and (
                    "[" in child.content or "](" in child.content
                ):
                    issues.append(
                        "P1 VALIDITY: memory-index contains "
                        "unresolved link syntax"
                    )
        destinations.extend(inline_destinations)
        linked_destinations.extend(inline_destinations)
        unparsed_text = "".join(plain_text).strip(" ,")
        if inside_file_cell and inline_destinations and unparsed_text:
            issues.append(
                "P1 VALIDITY: memory-index file cell contains "
                f"unparsed content: {unparsed_text!r}"
            )
        if inside_file_cell and not inline_destinations:
            file_entry = "".join(plain_text).strip()
            if file_entry:
                destinations.extend(
                    item.strip()
                    for item in file_entry.split(",")
                    if item.strip()
                )

    def normalize_destinations(
        values: list[str],
        *,
        record_issues: bool,
    ) -> list[str]:
        reference_names: list[str] = []
        for destination in values:
            invalid_reason = _invalid_destination_reason(destination)
            if invalid_reason:
                if record_issues:
                    issues.append(
                        f"P1 VALIDITY: memory-index destination "
                        f"{destination!r} contains {invalid_reason}"
                    )
                continue
            reference_names.append(
                re.sub(r"\.md$", "", destination, flags=re.IGNORECASE)
            )
        return reference_names

    return (
        normalize_destinations(destinations, record_issues=True),
        normalize_destinations(linked_destinations, record_issues=False),
        issues,
    )


def _canonical_reference_counts(
    content: str,
    memory_path: Path,
) -> tuple[Counter[str] | None, str | None]:
    """Count safe canonical references, or return a closed failure."""
    reference_names, _, issues = _extract_memory_reference_names(content)
    if issues:
        return None, issues[0]

    resolved_memory = memory_path.resolve()
    canonical_refs: list[str] = []
    for file_name in reference_names:
        canonical_identity, _, invalid_reason = _resolve_memory_reference(
            memory_path,
            resolved_memory,
            file_name,
        )
        if canonical_identity is None:
            return None, (
                f"P1 VALIDITY: {invalid_reason} detected "
                f"in memory-index: {file_name}.md"
            )
        canonical_refs.append(canonical_identity)
    return Counter(canonical_refs), None


def _load_base_reference_counts(
    memory_path: Path,
    base_ref: str,
) -> tuple[Counter[str] | None, str | None]:
    """Read canonical memory-index counts from the current base ref."""
    if not base_ref or base_ref.startswith("-"):
        return None, f"invalid base ref: {base_ref!r}"

    git_env = os.environ.copy()
    for variable in (
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_PREFIX",
        "GIT_WORK_TREE",
    ):
        git_env.pop(variable, None)

    try:
        repo_root_result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=memory_path,
            env=git_env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if repo_root_result.returncode != 0:
            return None, "could not resolve repository root"
        repo_root = Path(repo_root_result.stdout.strip()).resolve()
        relative_index = (
            memory_path.resolve() / "memory-index.md"
        ).relative_to(repo_root).as_posix()

        base_commit_result = subprocess.run(
            [
                "git",
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{base_ref}^{{commit}}",
            ],
            cwd=repo_root,
            env=git_env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if base_commit_result.returncode != 0:
            return None, f"could not resolve base ref {base_ref}"
        base_commit = base_commit_result.stdout.strip()
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", base_commit):
            return None, f"base ref {base_ref} was not one commit ID"

        merge_base_result = subprocess.run(
            ["git", "merge-base", "HEAD", base_commit],
            cwd=repo_root,
            env=git_env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if merge_base_result.returncode != 0:
            return None, (
                f"could not resolve merge base between HEAD and {base_ref}"
            )
        base_commit = merge_base_result.stdout.strip()
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", base_commit):
            return None, (
                f"merge base between HEAD and {base_ref} "
                "was not one commit ID"
            )

        show_result = subprocess.run(
            ["git", "show", f"{base_commit}:{relative_index}"],
            cwd=repo_root,
            env=git_env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if show_result.returncode != 0:
            return None, (
                f"could not read {relative_index} at base ref {base_commit}"
            )

        relative_memory = posixpath.dirname(relative_index)
        tree_result = subprocess.run(
            [
                "git",
                "ls-tree",
                "-r",
                "-z",
                base_commit,
                "--",
                relative_memory,
            ],
            cwd=repo_root,
            env=git_env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if tree_result.returncode != 0:
            return None, (
                f"could not inspect {relative_memory} at base ref "
                f"{base_commit}"
            )
    except (OSError, ValueError) as exc:
        return None, f"could not read base memory index: {exc}"

    symlink_paths: set[str] = set()
    for entry in tree_result.stdout.split("\0"):
        if not entry:
            continue
        if "\t" not in entry:
            return None, "could not parse base-ref tree output"
        metadata, path = entry.split("\t", 1)
        mode = metadata.split(" ", 1)[0]
        if mode == "120000":
            symlink_paths.add(path)

    reference_names, _, destination_issues = (
        _extract_memory_reference_names(show_result.stdout)
    )
    if destination_issues:
        return None, destination_issues[0]
    for file_name in reference_names:
        raw_target_path = f"{relative_memory}/{file_name}.md"
        target_path = posixpath.normpath(raw_target_path)
        has_symlink_component = any(
            raw_target_path == symlink_path
            or raw_target_path.startswith(f"{symlink_path}/")
            or target_path == symlink_path
            or target_path.startswith(f"{symlink_path}/")
            for symlink_path in symlink_paths
        )
        if has_symlink_component:
            return None, (
                f"base memory-index target is a symbolic link: "
                f"{target_path}"
            )

    return _canonical_reference_counts(show_result.stdout, memory_path)


def find_domain_indices(memory_path: Path) -> list[DomainIndex]:
    """Find all domain index files."""
    if not memory_path.exists():
        return []

    indices: list[DomainIndex] = []
    for f in sorted(memory_path.glob("*-index.md")):
        if f.name == "memory-index.md":
            continue
        name = f.stem
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


# Kebab-case pattern: lowercase letters, digits, and hyphens only.
_KEBAB_CASE_PATTERN: re.Pattern[str] = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Directories are allowed to use simple lowercase names.
_ALLOWED_SPECIAL_NAMES: frozenset[str] = frozenset({
    "README",
    "CLAUDE",
})


def check_naming_convention(memory_path: Path) -> NamingConventionResult:
    """Validate that all memory files follow lowercase kebab-case naming.

    Scans all .md files under memory_path (recursively). Both directory
    names and filenames must use lowercase kebab-case:
    ``some-dir/some-file-name.md``. Known special names (README, CLAUDE)
    are excluded from the filename check only.
    """
    result = NamingConventionResult()

    if not memory_path.exists():
        return result

    for f in sorted(memory_path.rglob("*.md")):
        relative = f.relative_to(memory_path)

        # Check all path components for kebab-case compliance.
        is_violation = False
        for i, part in enumerate(relative.parts):
            is_last = i == len(relative.parts) - 1
            if is_last:
                stem = f.stem
                if stem in _ALLOWED_SPECIAL_NAMES:
                    continue
                if not _KEBAB_CASE_PATTERN.match(stem):
                    is_violation = True
            else:
                if not _KEBAB_CASE_PATTERN.match(part):
                    is_violation = True

            if is_violation:
                break

        if is_violation:
            result.passed = False
            rel_posix = relative.as_posix()
            result.violations.append(rel_posix)
            result.issues.append(
                f"Naming violation: {rel_posix} is not lowercase "
                f"kebab-case (expected pattern: lowercase-with-hyphens)"
            )

    return result


def _parse_leading_frontmatter(
    text: str,
) -> tuple[bool, object, str | None]:
    """Parse a leading YAML frontmatter block directly.

    Returns ``(has_frontmatter, metadata, error)``:

    - ``(False, None, None)`` when the file has no leading frontmatter block.
      Frontmatter is optional (issue #4900), so plain Markdown, or a file whose
      only ``---`` is a horizontal rule in the body, is not frontmatter.
    - ``(True, metadata, None)`` when a closed block parsed successfully.
      ``metadata`` is whatever YAML produced (dict, list, scalar, or None).
    - ``(True, None, error)`` when the opening delimiter never closes or the
      block is not parseable YAML. ``error`` is a one-line reason.

    Stricter than ``frontmatter.loads``, which silently returns empty metadata
    for an unclosed delimiter, a list, or a scalar (issue #4918). Detection
    keys on the first line being exactly ``---`` so a horizontal rule later in
    the body is never misread as frontmatter.
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---":
        return False, None, None
    for idx in range(1, len(lines)):
        if lines[idx].rstrip() == "---":
            block = "\n".join(lines[1:idx])
            try:
                metadata = yaml.safe_load(block)
            except yaml.YAMLError as exc:
                detail = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
                return True, None, detail
            return True, metadata, None
    return True, None, "unclosed frontmatter delimiter (missing closing '---')"


def check_frontmatter_validity(memory_path: Path) -> FrontmatterResult:
    """Validate that leading YAML frontmatter parses on every memory file.

    Scans all .md files under memory_path (recursively). A file that opens with
    a frontmatter block (first line exactly ``---``) must close that block and
    carry a YAML mapping. A file with no leading frontmatter is fine:
    frontmatter is optional in existing Serena memories (issue #4900), so a
    plain-Markdown file, or one with a later horizontal rule, is not a
    violation.

    Three malformed shapes that ``frontmatter.loads`` accepted as empty
    metadata are now violations (issue #4918): an unclosed opening delimiter, a
    block that parses to a list, and a block that parses to a scalar. An empty
    block (``None``) stays valid because it carries no colon-space corruption.
    """
    result = FrontmatterResult()

    if not memory_path.exists():
        return result

    for f in sorted(memory_path.rglob("*.md")):
        relative = f.relative_to(memory_path)
        if any(part.startswith(".") for part in relative.parts):
            continue
        has_frontmatter, metadata, error = _parse_leading_frontmatter(
            f.read_text(encoding="utf-8")
        )
        if not has_frontmatter:
            continue
        rel_posix = relative.as_posix()
        if error is not None:
            result.passed = False
            result.invalid_files.append(rel_posix)
            result.issues.append(
                f"Malformed YAML frontmatter: {rel_posix} ({error}). "
                f"Quote values that contain a colon-space, close the block with "
                f"a '---' delimiter, or remove the frontmatter block."
            )
            continue
        if metadata is not None and not isinstance(metadata, dict):
            result.passed = False
            result.invalid_files.append(rel_posix)
            result.issues.append(
                f"Malformed YAML frontmatter: {rel_posix} (frontmatter must be "
                f"a mapping, got {type(metadata).__name__}). Use 'key: value' "
                f"lines, or remove the frontmatter block."
            )

    return result


# ---------------------------------------------------------------------------
# P1 validators
# ---------------------------------------------------------------------------


def check_memory_index_references(
    memory_path: Path,
    domain_indices: list[DomainIndex],
    base_reference_counts: Counter[str] | None = None,
) -> MemoryIndexRefResult:
    """Validate that memory-index references existing domain indices.

    P1 validations:
    1. All domain indices MUST be referenced in memory-index (completeness)
    2. All references in memory-index MUST point to existing files (validity)
    """
    result = MemoryIndexRefResult()
    base_reference_counts = base_reference_counts or Counter()
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

    reference_names, linked_reference_names, destination_issues = (
        _extract_memory_reference_names(content)
    )
    if destination_issues:
        result.passed = False
        result.issues.extend(destination_issues)

    canonical_refs: list[str] = []
    resolved_refs: dict[str, Path] = {}
    for file_name in reference_names:
        canonical_identity, resolved_ref, invalid_reason = (
            _resolve_memory_reference(
            memory_path,
            resolved_memory,
            file_name,
            )
        )
        if canonical_identity is None:
            result.passed = False
            result.broken_references.append(file_name)
            result.issues.append(
                f"P1 VALIDITY: {invalid_reason} detected "
                f"in memory-index: {file_name}.md"
            )
            continue

        canonical_refs.append(canonical_identity)
        resolved_refs.setdefault(canonical_identity, resolved_ref)

    linked_canonical_refs: set[str] = set()
    for file_name in linked_reference_names:
        canonical_identity, _, _ = _resolve_memory_reference(
            memory_path,
            resolved_memory,
            file_name,
        )
        if canonical_identity is not None:
            linked_canonical_refs.add(canonical_identity)

    domain_index_names = {index.name for index in domain_indices}
    domain_index_names.update(
        path.stem
        for path in memory_path.glob("*-index.md")
        if path.name != "memory-index.md"
    )
    for index_name in sorted(domain_index_names):
        canonical_index, _, _ = _resolve_memory_reference(
            memory_path,
            resolved_memory,
            index_name,
        )
        if canonical_index not in linked_canonical_refs:
            result.passed = False
            result.unreferenced_indices.append(index_name)
            result.issues.append(
                f"P1 COMPLETENESS: Domain index not referenced "
                f"in memory-index: {index_name}"
            )

    reference_counts = Counter(canonical_refs)
    for file_name, observed_count in reference_counts.items():
        allowed_count = max(base_reference_counts.get(file_name, 0), 1)
        if observed_count > allowed_count:
            result.passed = False
            result.duplicate_references.append(file_name)
            result.issues.append(
                f"P0 DUPLICATE: Duplicate memory-index target: "
                f"{file_name}.md referenced {observed_count} times, "
                f"allowed {allowed_count}"
            )

    for file_name, resolved_ref in resolved_refs.items():
        if not resolved_ref.exists():
            result.passed = False
            result.broken_references.append(file_name)
            result.issues.append(
                f"P1 VALIDITY: memory-index references "
                f"non-existent file: {file_name}.md"
            )

    return result


def _memory_domain(relative_path: Path) -> str:
    """Return the retrieval domain for a memory path."""
    if len(relative_path.parts) > 1:
        return relative_path.parts[0]
    return relative_path.stem.split("-", 1)[0]


def _validate_orphan_policy(orphan_policy: str) -> OrphanPolicy:
    """Return a supported orphan policy or reject a caller error."""
    if orphan_policy not in {"strict", "ratchet"}:
        raise ValueError(f"Unsupported orphan policy: {orphan_policy}")
    return "strict" if orphan_policy == "strict" else "ratchet"


def _memory_index_blocks(result: MemoryIndexRefResult) -> bool:
    """Return whether memory-index findings should fail this consumer."""
    return not result.passed


def find_orphaned_files(
    all_indices: list[DomainIndex], memory_path: Path
) -> list[Orphan]:
    """Find atomic memories not referenced by the root or a domain index."""
    referenced_files: set[str] = set()
    owner_counts: dict[str, dict[str, int]] = {}

    index_paths = [
        path
        for path in memory_path.glob("*-index.md")
        if path.name != "memory-index.md"
    ]
    root_index = memory_path / "memory-index.md"
    if root_index.exists():
        index_paths.append(root_index)

    resolved_root = memory_path.resolve()
    for index_path in index_paths:
        content = index_path.read_text(encoding="utf-8")
        reference_names, _, issues = _extract_memory_reference_names(content)
        if issues:
            continue
        index_references: set[str] = set()
        for reference in reference_names:
            canonical, _, invalid_reason = _resolve_memory_reference(
                memory_path,
                resolved_root,
                reference,
            )
            if invalid_reason:
                continue
            referenced_name = f"{canonical}.md"
            referenced_files.add(referenced_name)
            index_references.add(referenced_name)

        if index_path == root_index:
            continue
        for reference in index_references:
            reference_path = Path(reference)
            domain = _memory_domain(reference_path)
            domain_counts = owner_counts.setdefault(domain, {})
            domain_counts[index_path.name] = (
                domain_counts.get(index_path.name, 0) + 1
            )

    orphans: list[Orphan] = []
    for file_path in sorted(memory_path.rglob("*.md")):
        relative_path = file_path.relative_to(memory_path)
        if any(part.startswith(".") for part in relative_path.parts):
            continue
        if file_path.name in _SPECIAL_MEMORY_FILENAMES:
            continue
        if (
            len(relative_path.parts) == 1
            and _DOMAIN_INDEX_FILENAME_PATTERN.match(file_path.name)
        ):
            continue

        relative_name = relative_path.as_posix()
        if relative_name in referenced_files:
            continue

        file_name = relative_path.with_suffix("").as_posix()
        if file_path.stem.startswith("skill-"):
            orphans.append(
                Orphan(
                    file=file_name,
                    domain="INVALID",
                    expected_index=(
                        "Rename to {domain}-{description} "
                        "format per ADR-017"
                    ),
                )
            )
            continue

        if file_path.stem.startswith("skills-"):
            orphans.append(
                Orphan(
                    file=file_name,
                    domain="INVALID",
                    expected_index=(
                        "Rename to {domain}-{description}-index format "
                        "or move to atomic file per ADR-017"
                    ),
                )
            )
            continue

        domain = _memory_domain(relative_path)
        domain_counts = owner_counts.get(domain, {})
        expected_index = (
            min(
                domain_counts,
                key=lambda name: (-domain_counts[name], name),
            )
            if domain_counts
            else "a domain index referenced by memory-index.md"
        )
        orphans.append(
            Orphan(
                file=file_name,
                domain=domain,
                expected_index=expected_index,
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


def run_validation(
    memory_path: Path,
    output_format: str,
    base_reference_counts: Counter[str],
    *,
    orphan_policy: OrphanPolicy = "strict",
) -> ValidationReport:
    """Run full memory index validation."""
    from datetime import UTC, datetime

    orphan_policy = _validate_orphan_policy(orphan_policy)
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

        is_skills_index = bool(
            _SKILLS_DOMAIN_INDEX_FILENAME_PATTERN.match(index.path.name)
        )
        keyword_result = (
            check_keyword_density(entries)
            if is_skills_index
            else KeywordDensityResult()
        )
        if not keyword_result.passed:
            report.summary.keyword_issues += len(keyword_result.issues)

        format_result = check_index_format(index.path)
        duplicate_result = (
            check_duplicate_entries(entries)
            if is_skills_index
            else DuplicateResult()
        )

        # P2 validations
        min_kw_result = (
            check_minimum_keywords(entries, min_keywords=5)
            if is_skills_index
            else ValidationIssues()
        )
        prefix_result = (
            check_domain_prefix_naming(entries, index.domain)
            if is_skills_index
            else ValidationIssues()
        )

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
        memory_path,
        domain_indices,
        base_reference_counts,
    )
    report.memory_index_result = memory_index_result

    if _memory_index_blocks(memory_index_result):
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
    orphans.extend(
        Orphan(
            file=index_name,
            domain="INDEX",
            expected_index="memory-index.md",
        )
        for index_name in memory_index_result.unreferenced_indices
    )
    report.orphans = orphans

    if orphans and orphan_policy == "strict":
        report.passed = False
    if orphans and output_format == "console":
        print("\n[P1] Orphaned files detected (not indexed):")
        for orphan in orphans:
            print(
                f"  - {orphan.file} (should be in {orphan.expected_index})"
            )

    # P1: Naming convention enforcement (kebab-case)
    naming_result = check_naming_convention(memory_path)
    report.naming_convention = naming_result

    if not naming_result.passed:
        report.passed = False
        if output_format == "console":
            print(
                f"\n[P1] Naming convention violations "
                f"({len(naming_result.violations)}):"
            )
            for issue in naming_result.issues:
                print(f"  - {issue}")

    # P0: Frontmatter YAML validity (issue #4918)
    frontmatter_result = check_frontmatter_validity(memory_path)
    report.frontmatter_validity = frontmatter_result

    if not frontmatter_result.passed:
        report.passed = False
        if output_format == "console":
            print(
                f"\n[P0] Malformed frontmatter "
                f"({len(frontmatter_result.invalid_files)}):"
            )
            for issue in frontmatter_result.issues:
                print(f"  - {issue}")

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
        lines.append("")

    if report.naming_convention and report.naming_convention.violations:
        lines.append("## Naming Convention Violations")
        lines.append("")
        for v in report.naming_convention.violations:
            lines.append(f"- {v}")
        lines.append("")

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
    parser.add_argument(
        "--base-ref",
        default=os.environ.get("BASE_REF", "origin/main"),
        help=(
            "Git base ref for duplicate-count ratchet "
            "(env: BASE_REF, default: origin/main)"
        ),
    )
    parser.add_argument(
        "--orphan-policy",
        choices=["strict", "ratchet"],
        default="strict",
        help=(
            "Orphan handling: strict fails on any orphan; ratchet reports "
            "orphans while the separate count ratchet blocks growth"
        ),
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

    base_reference_counts, base_error = _load_base_reference_counts(
        target,
        args.base_ref,
    )
    if base_reference_counts is None:
        if args.output_format == "console":
            print(f"Base memory index unavailable: {base_error}")
        return 2

    orphan_policy = args.orphan_policy
    if args.ci and orphan_policy == "strict":
        orphan_policy = "ratchet"

    report = run_validation(
        target,
        args.output_format,
        base_reference_counts,
        orphan_policy=orphan_policy,
    )

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
