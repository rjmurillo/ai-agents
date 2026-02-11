#!/usr/bin/env python3
"""Check GitHub API rate limits before workflow execution.

Thin CLI wrapper around ``check_workflow_rate_limit`` from the shared
``github_core`` library.  Designed for GitHub Actions workflow integration
per ADR-006 (thin workflows, testable modules).

Exit codes (ADR-035):
    0 - Sufficient rate limit remaining to proceed.
    1 - Rate limit too low or check failed.
"""

from __future__ import annotations

import argparse
import os
import sys

workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
sys.path.insert(0, workspace)

from scripts.github_core.api import check_workflow_rate_limit  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Run rate-limit check and emit GitHub Actions outputs."""
    parser = argparse.ArgumentParser(
        description="Check GitHub API rate limits before workflow execution.",
    )
    parser.add_argument(
        "--core-threshold",
        type=int,
        default=100,
        help="Minimum remaining core API calls (default: 100)",
    )
    parser.add_argument(
        "--graphql-threshold",
        type=int,
        default=50,
        help="Minimum remaining GraphQL API calls (default: 50)",
    )
    args = parser.parse_args(argv)

    thresholds = {
        "core": args.core_threshold,
        "graphql": args.graphql_threshold,
    }

    try:
        result = check_workflow_rate_limit(resource_thresholds=thresholds)
    except RuntimeError as exc:
        print(f"Failed to check rate limits: {exc}", file=sys.stderr)
        return 1

    print(
        f"Rate limits - Core: {result.core_remaining}, "
        f"Thresholds: core={args.core_threshold}, "
        f"graphql={args.graphql_threshold}"
    )
    print(result.summary_markdown)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write(f"core_remaining={result.core_remaining}\n")

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(result.summary_markdown + "\n")

    if not result.success:
        print("Rate limit too low to proceed", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
