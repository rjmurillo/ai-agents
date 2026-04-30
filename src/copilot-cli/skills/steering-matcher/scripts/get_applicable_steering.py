#!/usr/bin/env python3
"""Match file paths against steering file glob patterns.

Analyzes file paths and returns applicable steering files based on glob
pattern matching. Steering files are sorted by priority (higher first).

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
"""

from __future__ import annotations

import argparse
import json
import re
from fnmatch import translate as fnmatch_translate
from pathlib import Path


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Convert a glob pattern to a compiled regex.

    Handles ** (globstar) for recursive directory matching,
    * for single-level matching, and ? for single-char matching.
    """
    # Normalize path separators
    pattern = pattern.replace("\\", "/")

    # Handle globstar patterns before fnmatch processing
    # Replace ** with special placeholders
    pattern = pattern.replace("**/", "\x00GLOBSTAR_SLASH\x00")
    pattern = pattern.replace("/**", "\x00SLASH_GLOBSTAR\x00")

    # Check for standalone ** at start/end
    if pattern.startswith("**"):
        pattern = "\x00START_GLOBSTAR\x00" + pattern[2:]
    if pattern.endswith("**"):
        pattern = pattern[:-2] + "\x00END_GLOBSTAR\x00"

    # Use fnmatch for basic glob-to-regex conversion
    regex = fnmatch_translate(pattern)

    # Strip the \Z (end anchor) that fnmatch adds so we can reconstruct
    regex = regex.removesuffix(r"\Z")

    # Replace placeholders with proper regex
    regex = regex.replace(r"\x00GLOBSTAR_SLASH\x00", "(?:.+/|)")
    regex = regex.replace(r"\x00SLASH_GLOBSTAR\x00", "/.*")
    regex = regex.replace(r"\x00START_GLOBSTAR\x00", ".*")
    regex = regex.replace(r"\x00END_GLOBSTAR\x00", ".*")

    return re.compile(f"^{regex}$")


def _file_matches_patterns(file_path: str, patterns: list[str]) -> bool:
    """Test if a file path matches any of the given glob patterns."""
    normalized = file_path.replace("\\", "/")
    for pattern in patterns:
        normalized_pattern = pattern.replace("\\", "/")
        regex = _glob_to_regex(normalized_pattern)
        if regex.match(normalized):
            return True
    return False


def get_applicable_steering(
    files: list[str],
    steering_path: str = ".agents/steering",
) -> list[dict]:
    """Return steering files applicable to the given file paths.

    Args:
        files: List of file paths to analyze.
        steering_path: Path to the steering directory.

    Returns:
        List of dicts with Name, Path, ApplyTo, ExcludeFrom, Priority,
        sorted by priority descending.
    """
    if not files:
        return []

    steering_dir = Path(steering_path)
    if not steering_dir.is_dir():
        return []

    # Front matter regex
    front_matter_re = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)

    applicable: list[dict] = []

    for md_file in sorted(steering_dir.glob("*.md")):
        if md_file.name in ("README.md", "SKILL.md"):
            continue

        content = md_file.read_text(encoding="utf-8")
        fm_match = front_matter_re.match(content)
        if not fm_match:
            continue

        front_matter = fm_match.group(1)

        # Parse applyTo
        apply_match = re.search(r'applyTo:\s*"([^"]+)"', front_matter)
        if not apply_match:
            continue
        apply_to = apply_match.group(1)

        # Parse excludeFrom (optional)
        exclude_match = re.search(r'excludeFrom:\s*"([^"]+)"', front_matter)
        exclude_from = exclude_match.group(1) if exclude_match else None

        # Parse priority (default 5)
        priority_match = re.search(r"priority:\s*(\d+)", front_matter)
        priority = int(priority_match.group(1)) if priority_match else 5

        include_patterns = [p.strip() for p in apply_to.split(",")]
        exclude_patterns = (
            [p.strip() for p in exclude_from.split(",")]
            if exclude_from
            else []
        )

        for file_path in files:
            matches_include = _file_matches_patterns(file_path, include_patterns)
            matches_exclude = (
                _file_matches_patterns(file_path, exclude_patterns)
                if exclude_patterns
                else False
            )

            if matches_include and not matches_exclude:
                applicable.append({
                    "name": md_file.stem,
                    "path": str(md_file.resolve()),
                    "apply_to": apply_to,
                    "exclude_from": exclude_from,
                    "priority": priority,
                })
                break  # One file match is enough to include this steering file

    # Sort by priority descending
    applicable.sort(key=lambda x: x["priority"], reverse=True)
    return applicable


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Match file paths against steering file glob patterns.",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        required=True,
        help="File paths to analyze",
    )
    parser.add_argument(
        "--steering-path",
        default=".agents/steering",
        help="Path to the steering directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = get_applicable_steering(args.files, args.steering_path)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
