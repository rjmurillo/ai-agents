#!/usr/bin/env python3
"""
Validate Serena memory file sizes against context engineering thresholds.

Enforces atomicity constraints from memory-size-001-decomposition-thresholds:
- Max 10,000 chars (~2,500 tokens)
- Max 15 skills per file
- Max 3-5 categories per file
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


def validate_path_no_traversal(path: Path) -> Path:
    """Validate path has no traversal patterns (CWE-22 protection).

    Rejects '..' components and resolves to canonical form.
    Relative paths must resolve within the current working directory.
    Absolute paths are allowed (OS permissions provide access control).
    """
    if ".." in str(path):
        raise PermissionError(
            f"Path traversal detected: '{path}' contains '..'"
        )
    resolved = path.resolve()
    if not path.is_absolute():
        try:
            resolved.relative_to(Path.cwd().resolve())
        except ValueError as exc:
            raise PermissionError(
                f"Path '{path}' resolves outside working directory"
            ) from exc
    return resolved


@dataclass
class ValidationResult:
    """Memory file validation result."""
    file_path: str
    is_valid: bool
    char_count: int
    skill_count: int
    category_count: int
    violations: list[str]
    recommendation: str | None = None


class MemorySizeValidator:
    """Validator for memory file sizes and structure."""

    # Thresholds from memory-size-001-decomposition-thresholds
    MAX_CHARS = 10_000
    MAX_SKILLS = 15
    MAX_CATEGORIES = 5

    def __init__(
        self,
        max_chars: int = MAX_CHARS,
        max_skills: int = MAX_SKILLS,
        max_categories: int = MAX_CATEGORIES
    ):
        self.max_chars = max_chars
        self.max_skills = max_skills
        self.max_categories = max_categories

    def validate_file(self, file_path: Path) -> ValidationResult:
        """
        Validate a single memory file.

        Args:
            file_path: Path to memory markdown file

        Returns:
            ValidationResult with detailed findings
        """
        file_path = validate_path_no_traversal(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Memory file not found: {file_path}")

        content = file_path.read_text(encoding="utf-8")

        # Count characters
        char_count = len(content)

        # Count skills (## level-2 headings)
        skill_count = len(re.findall(r'^## ', content, re.MULTILINE))

        # Count categories (heuristic: unique tags or top-level sections)
        # Look for common category markers: tags, labels, or h1 sections
        category_count = self._count_categories(content)

        # Check violations
        violations = []
        if char_count > self.max_chars:
            violations.append(
                f"Character count ({char_count:,}) exceeds maximum ({self.max_chars:,})"
            )

        if skill_count > self.max_skills:
            violations.append(
                f"Skill count ({skill_count}) exceeds maximum ({self.max_skills})"
            )

        if category_count > self.max_categories:
            violations.append(
                f"Category count ({category_count}) exceeds maximum ({self.max_categories})"
            )

        # Generate recommendation
        recommendation = None
        if violations:
            if char_count > self.max_chars:
                files_needed = (char_count + self.max_chars - 1) // self.max_chars
                recommendation = (
                    f"Decompose into {files_needed} focused files. "
                    f"Target <{self.max_chars:,} chars per file. "
                    f"See memory-size-001-decomposition-thresholds.md"
                )
            elif skill_count > self.max_skills:
                recommendation = (
                    f"Split into {(skill_count + self.max_skills - 1) // self.max_skills} "
                    f"files, grouping related skills. Target ≤{self.max_skills} skills per file."
                )
            elif category_count > self.max_categories:
                recommendation = (
                    f"Reduce to {self.max_categories} categories or split into "
                    f"category-specific files."
                )

        return ValidationResult(
            file_path=str(file_path),
            is_valid=len(violations) == 0,
            char_count=char_count,
            skill_count=skill_count,
            category_count=category_count,
            violations=violations,
            recommendation=recommendation
        )

    def _count_categories(self, content: str) -> int:
        """
        Count categories in memory file using heuristics.

        Categories can be:
        1. H1 sections (# Category Name)
        2. Tags in frontmatter or metadata
        3. Distinct top-level concept groups
        """
        # Count H1 headings (excluding title)
        h1_headings = re.findall(r'^# (.+)$', content, re.MULTILINE)

        # Exclude common non-category headings
        excluded = {'toc', 'table of contents', 'overview', 'introduction'}
        categories = [h for h in h1_headings if h.lower() not in excluded]

        # If no H1s, use H2 groupings as proxy
        if not categories:
            # Group H2s by common prefixes (e.g., "Git: ", "GitHub: ")
            h2_headings = re.findall(r'^## (.+)$', content, re.MULTILINE)
            prefixes = set()
            for h2 in h2_headings:
                # Extract prefix before colon or hyphen
                match = re.match(r'^([^:-]+)[:-]', h2)
                if match:
                    prefixes.add(match.group(1).strip())
            return len(prefixes) if prefixes else 1  # At least 1 category

        return len(categories)

    def validate_directory(
        self,
        directory: Path,
        pattern: str = "*.md",
        recursive: bool = False
    ) -> list[ValidationResult]:
        """
        Validate all memory files in directory.

        Args:
            directory: Directory containing memory files
            pattern: Glob pattern for files
            recursive: Recursively process subdirectories

        Returns:
            List of ValidationResult objects
        """
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        glob_pattern = f"**/{pattern}" if recursive else pattern
        results = []

        failed = 0
        for file_path in sorted(directory.glob(glob_pattern)):
            if file_path.is_file():
                try:
                    result = self.validate_file(file_path)
                    results.append(result)
                except (FileNotFoundError, PermissionError, UnicodeDecodeError, OSError) as e:
                    print(f"Warning: Failed to validate {file_path}: {e}", file=sys.stderr)
                    failed += 1

        if failed:
            print(f"Warning: {failed} file(s) skipped due to errors", file=sys.stderr)

        return results


def format_result(result: ValidationResult, verbose: bool = False) -> str:
    """Format validation result for display."""
    status = "✅ PASS" if result.is_valid else "❌ FAIL"

    lines = [
        f"{status}: {result.file_path}",
        f"  Characters: {result.char_count:,}",
        f"  Skills: {result.skill_count}",
        f"  Categories: {result.category_count}"
    ]

    if not result.is_valid:
        lines.append("  Violations:")
        for violation in result.violations:
            lines.append(f"    - {violation}")

        if result.recommendation:
            lines.append(f"  Recommendation: {result.recommendation}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Validate Serena memory file sizes against context engineering thresholds"
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Memory file or directory to validate"
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Recursively process directory"
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.md",
        help="File pattern for directory mode (default: *.md)"
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=MemorySizeValidator.MAX_CHARS,
        help=f"Maximum character count (default: {MemorySizeValidator.MAX_CHARS:,})"
    )
    parser.add_argument(
        "--max-skills",
        type=int,
        default=MemorySizeValidator.MAX_SKILLS,
        help=f"Maximum skills per file (default: {MemorySizeValidator.MAX_SKILLS})"
    )
    parser.add_argument(
        "--max-categories",
        type=int,
        default=MemorySizeValidator.MAX_CATEGORIES,
        help=f"Maximum categories per file (default: {MemorySizeValidator.MAX_CATEGORIES})"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Exit on first validation failure"
    )

    args = parser.parse_args()

    try:
        args.path = validate_path_no_traversal(args.path)
    except PermissionError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    validator = MemorySizeValidator(
        max_chars=args.max_chars,
        max_skills=args.max_skills,
        max_categories=args.max_categories
    )

    try:
        if args.path.is_file():
            # Single file mode
            result = validator.validate_file(args.path)
            print(format_result(result, args.verbose))
            sys.exit(0 if result.is_valid else 1)

        elif args.path.is_dir():
            # Directory mode
            results = validator.validate_directory(
                args.path,
                args.pattern,
                args.recursive
            )

            if not results:
                print(f"No files matching '{args.pattern}' in {args.path}", file=sys.stderr)
                sys.exit(1)

            # Print results
            failed_count = 0
            for result in results:
                print(format_result(result, args.verbose))
                print()  # Blank line between files

                if not result.is_valid:
                    failed_count += 1
                    if args.fail_fast:
                        sys.exit(1)

            # Summary
            total = len(results)
            passed = total - failed_count
            print(f"Summary: {passed}/{total} files passed validation")

            if failed_count > 0:
                print(f"\n❌ {failed_count} file(s) exceeded size thresholds")
                print("Run decomposition to fix (see memory-size-001-decomposition-thresholds.md)")
                sys.exit(1)
            else:
                print("\n✅ All files within size thresholds")
                sys.exit(0)

        else:
            print(f"Error: Path not found: {args.path}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
