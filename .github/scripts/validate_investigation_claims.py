#!/usr/bin/env python3
"""Validate investigation-only claims against the shared allowlist.

CI backstop for ADR-034: re-validates that commits claiming investigation-only
status only modified files within the investigation allowlist. Advisory only,
logs violations for metrics without blocking.

Input env vars (used as defaults for CLI args):
    GITHUB_OUTPUT    - Path to GitHub Actions output file
    GITHUB_WORKSPACE - Workspace root (for package imports)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
sys.path.insert(0, workspace)

from scripts.ai_review_common import write_log, write_output  # noqa: E402
from scripts.modules.investigation_allowlist import (  # noqa: E402
    get_investigation_allowlist_display,
    test_file_matches_allowlist,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Validate investigation-only claims against the shared allowlist.",
    )
    parser.add_argument(
        "--base-ref",
        default="HEAD~1",
        help="Base ref for diff comparison (default: HEAD~1)",
    )
    parser.add_argument(
        "--head-ref",
        default="HEAD",
        help="Head ref for diff comparison (default: HEAD)",
    )
    return parser


def get_changed_files(base_ref: str, head_ref: str) -> list[str]:
    """Get list of changed files between two refs."""
    result = subprocess.run(
        ["git", "diff", "--name-only", base_ref, head_ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        write_log(f"WARNING: git diff failed: {result.stderr.strip()}")
        return []
    return [f for f in result.stdout.strip().split("\n") if f]


def validate_claims(changed_files: list[str]) -> list[str]:
    """Return files that violate the investigation-only allowlist."""
    return [f for f in changed_files if not test_file_matches_allowlist(f)]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    changed_files = get_changed_files(args.base_ref, args.head_ref)
    if not changed_files:
        write_log("No changed files found.")
        write_output("investigation_violations", "0")
        write_output("violation_details", "")
        return 0

    write_log(f"Checking {len(changed_files)} changed file(s) against allowlist")

    violations = validate_claims(changed_files)

    write_output("investigation_violations", str(len(violations)))

    if violations:
        details = "\n".join(f"  - {v}" for v in violations)
        write_output("violation_details", details)
        write_log(f"Investigation-only claim violated by {len(violations)} file(s):")
        for v in violations:
            write_log(f"  {v}")
        write_log("")
        write_log("Allowed paths:")
        for path in get_investigation_allowlist_display():
            write_log(f"  {path}")
        print(
            f"::warning::Investigation-only claim violated by {len(violations)} file(s). "
            "This is advisory only.",
            file=sys.stderr,
        )
    else:
        write_output("violation_details", "")
        write_log("All changed files match investigation-only allowlist.")

    # Advisory only: always exit 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
