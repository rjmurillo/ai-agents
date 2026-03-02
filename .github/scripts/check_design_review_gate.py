#!/usr/bin/env python3
"""Check design review files for blocking verdicts that should prevent merge.

Parses DESIGN-REVIEW-*.md files in .agents/architecture/ for blocking
verdicts. Supports both YAML frontmatter and markdown header formats.

Exit codes (ADR-035):
    0 - All reviews pass (no blocking verdicts)
    1 - Blocking verdicts found
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from glob import glob
from typing import TextIO

# Verdicts that block merge
BLOCKING_VERDICTS = frozenset({
    "NEEDS_CHANGES",
    "FAIL",
    "REJECTED",
})

# Verdicts that pass the gate
PASSING_VERDICTS = frozenset({
    "PASS",
    "APPROVED",
    "CONCERNS",
    "NEEDS_ADR",
    "WARNING",
    "COMPLETE",
})

# Pattern to extract YAML frontmatter
_FRONTMATTER_RE = re.compile(r"\A---\n(.+?)\n---", re.DOTALL)

# Patterns for markdown header fields
_VERDICT_RE = re.compile(
    r"\*{2}(?:Verdict|VERDICT)\*{2}\s*:\s*\[?\s*(\w+)",
    re.IGNORECASE,
)
_STATUS_RE = re.compile(
    r"\*{2}Status\*{2}\s*:\s*\[?\s*(\w+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReviewResult:
    """Parsed result from a single design review file."""

    file_path: str
    verdict: str
    is_blocking: bool


def parse_yaml_frontmatter(content: str) -> dict[str, str]:
    """Extract key-value pairs from YAML frontmatter without pyyaml dependency."""
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def extract_verdict(content: str) -> str:
    """Extract the verdict from a design review file.

    Checks YAML frontmatter first, then falls back to markdown headers.
    Returns the normalized verdict string or empty string if not found.
    """
    frontmatter = parse_yaml_frontmatter(content)
    if frontmatter.get("status"):
        return frontmatter["status"].upper()

    for pattern in (_VERDICT_RE, _STATUS_RE):
        match = pattern.search(content)
        if match:
            return match.group(1).upper()

    return ""


def check_review_file(file_path: str) -> ReviewResult:
    """Parse a single design review file and determine if it blocks merge."""
    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    verdict = extract_verdict(content)
    is_blocking = verdict in BLOCKING_VERDICTS

    return ReviewResult(
        file_path=file_path,
        verdict=verdict,
        is_blocking=is_blocking,
    )


def find_design_reviews(base_dir: str) -> list[str]:
    """Find all DESIGN-REVIEW-*.md files in the architecture directory."""
    pattern = os.path.join(base_dir, ".agents", "architecture", "DESIGN-REVIEW-*.md")
    return sorted(glob(pattern))


def write_output(key: str, value: str) -> None:
    """Write a key-value pair to GITHUB_OUTPUT if available."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def run_gate(
    base_dir: str,
    output: TextIO = sys.stdout,
) -> int:
    """Run the synthesis panel gate check.

    Returns 0 if all reviews pass, 1 if any blocking verdicts found.
    """
    review_files = find_design_reviews(base_dir)

    if not review_files:
        output.write("No design review files found. Gate passes.\n")
        write_output("gate_result", "PASS")
        write_output("blocking_count", "0")
        return 0

    results = [check_review_file(f) for f in review_files]
    blocking = [r for r in results if r.is_blocking]

    output.write(f"Found {len(results)} design review file(s).\n")
    for r in results:
        status = "BLOCKED" if r.is_blocking else "OK"
        relative = os.path.relpath(r.file_path, base_dir)
        output.write(f"  [{status}] {relative}: {r.verdict or 'NO_VERDICT'}\n")

    write_output("gate_result", "FAIL" if blocking else "PASS")
    write_output("blocking_count", str(len(blocking)))

    if blocking:
        output.write(f"\n{len(blocking)} blocking review(s) found:\n")
        for r in blocking:
            relative = os.path.relpath(r.file_path, base_dir)
            output.write(f"  - {relative} ({r.verdict})\n")
        output.write("\nResolve blocking reviews before merging.\n")
        return 1

    output.write("\nAll design reviews pass. Gate approved.\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Check design review files for blocking verdicts.",
    )
    parser.add_argument(
        "--base-dir",
        default=os.environ.get(
            "GITHUB_WORKSPACE",
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
        ),
        help="Repository root directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = build_parser().parse_args(argv)
    return run_gate(args.base_dir)


if __name__ == "__main__":
    sys.exit(main())
