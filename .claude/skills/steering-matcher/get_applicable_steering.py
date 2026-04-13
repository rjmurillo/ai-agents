#!/usr/bin/env python3
"""Match file paths against steering file glob patterns.

Analyzes file paths and returns applicable steering files based on
glob pattern matching. Steering files are sorted by priority (higher priority first).

EXIT CODES (ADR-035):
    0 - Success: Steering match completed
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def glob_to_regex(pattern: str) -> str:
    """Convert a glob pattern to a regex pattern."""
    p = pattern.replace("\\", "/")

    # Protect globstar patterns before processing single-char wildcards
    p = p.replace("**/", "<!GLOBSTAR_SLASH!>")
    p = p.replace("/**", "<!SLASH_GLOBSTAR!>")

    # Handle standalone ** at start/end
    if p.startswith("**"):
        p = "<!START_GLOBSTAR!>" + p[2:]
    if p.endswith("**"):
        p = p[:-2] + "<!END_GLOBSTAR!>"

    # Escape dots before processing wildcards
    p = p.replace(".", "\\.")

    # Convert single wildcards
    p = p.replace("?", ".")
    p = p.replace("*", "[^/]*")

    # Restore globstar patterns
    p = p.replace("<!GLOBSTAR_SLASH!>", "(?:.+/|)")
    p = p.replace("<!SLASH_GLOBSTAR!>", "/.*")
    p = p.replace("<!START_GLOBSTAR!>", ".*")
    p = p.replace("<!END_GLOBSTAR!>", ".*")

    return f"^{p}$"


def file_matches_pattern(file_path: str, patterns: list[str]) -> bool:
    """Test if a file matches any of the given glob patterns."""
    normalized = file_path.replace("\\", "/")
    for pattern in patterns:
        normalized_pattern = pattern.replace("\\", "/")
        regex = glob_to_regex(normalized_pattern)
        if re.match(regex, normalized):
            return True
    return False


def get_applicable_steering(
    files: list[str],
    steering_path: str = ".agents/steering",
) -> list[dict]:
    """Find applicable steering files for the given file paths.

    Returns list of dicts with Name, Path, ApplyTo, ExcludeFrom, Priority,
    sorted by priority descending.
    """
    if not files:
        return []

    steering_dir = Path(steering_path)
    if not steering_dir.exists():
        return []

    steering_files = [
        f
        for f in steering_dir.glob("*.md")
        if f.is_file() and f.name not in ("README.md", "SKILL.md")
    ]

    applicable: list[dict] = []

    for steering_file in steering_files:
        try:
            content = steering_file.read_text(encoding="utf-8")
        except OSError:
            continue

        fm_match = re.search(r"(?s)^---\s*\n(.*?)\n---", content)
        if not fm_match:
            continue

        front_matter = fm_match.group(1)

        apply_to_match = re.search(r'applyTo:\s*"([^"]+)"', front_matter)
        apply_to = apply_to_match.group(1) if apply_to_match else None

        exclude_match = re.search(r'excludeFrom:\s*"([^"]+)"', front_matter)
        exclude_from = exclude_match.group(1) if exclude_match else None

        priority_match = re.search(r"priority:\s*(\d+)", front_matter)
        priority = int(priority_match.group(1)) if priority_match else 5

        if not apply_to:
            continue

        include_patterns = [p.strip() for p in apply_to.split(",")]
        exclude_patterns = [p.strip() for p in exclude_from.split(",")] if exclude_from else []

        for file_path in files:
            matches_include = file_matches_pattern(file_path, include_patterns)
            matches_exclude = (
                file_matches_pattern(file_path, exclude_patterns)
                if exclude_patterns
                else False
            )

            if matches_include and not matches_exclude:
                applicable.append({
                    "Name": steering_file.stem,
                    "Path": str(steering_file.resolve()),
                    "ApplyTo": apply_to,
                    "ExcludeFrom": exclude_from,
                    "Priority": priority,
                })
                break  # Only need one file to match to include this steering file

    applicable.sort(key=lambda s: s["Priority"], reverse=True)
    return applicable


def main() -> int:
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Match file paths against steering"
        " file glob patterns",
    )
    parser.add_argument(
        "--files", nargs="+", required=True,
        help="File paths to analyze",
    )
    parser.add_argument(
        "--steering-path", default=".agents/steering",
        help="Path to steering directory",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    results = get_applicable_steering(args.files, args.steering_path)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        if not results:
            print("No applicable steering files found.")
        else:
            for s in results:
                print(f"Matched: {s['Name']} (Priority: {s['Priority']})")
                print(f"  ApplyTo: {s['ApplyTo']}")
                if s.get("ExcludeFrom"):
                    print(f"  ExcludeFrom: {s['ExcludeFrom']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
