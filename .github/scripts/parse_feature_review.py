#!/usr/bin/env python3
"""Parse feature review AI output into recommendation, assignees, and labels.

Input env vars (used as defaults for CLI args):
    RAW_OUTPUT       - AI output containing feature review structured response
    GITHUB_OUTPUT    - Path to GitHub Actions output file
    GITHUB_WORKSPACE - Workspace root (for package imports)
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

from scripts.ai_review_common import (  # noqa: E402
    get_feature_review_assignees,
    get_feature_review_labels,
    get_feature_review_recommendation,
    write_output,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Parse feature review AI output into structured fields.",
    )
    parser.add_argument(
        "--raw-output",
        default=os.environ.get("RAW_OUTPUT", ""),
        help="AI output containing feature review response",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raw_output: str = args.raw_output

    try:
        with open("/tmp/feature-review-output.txt", "w", encoding="utf-8") as f:
            f.write(raw_output)
    except OSError:
        pass

    recommendation = get_feature_review_recommendation(raw_output)
    assignees = get_feature_review_assignees(raw_output)
    labels = get_feature_review_labels(raw_output)

    write_output("recommendation", recommendation)
    write_output("assignees", assignees)
    write_output("labels", labels)

    return 0


if __name__ == "__main__":
    sys.exit(main())
