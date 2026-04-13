#!/usr/bin/env python3
"""Parse AI categorization output into validated labels and category.

Input env vars (used as defaults for CLI args):
    RAW_OUTPUT         - AI output containing labels and category JSON
    FALLBACK_LABELS    - Comma-separated fallback labels from composite action
    GITHUB_OUTPUT      - Path to GitHub Actions output file
    GITHUB_WORKSPACE   - Workspace root (for package imports)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
sys.path.insert(0, workspace)

from scripts.ai_review_common import (  # noqa: E402
    SAFE_NAME_PATTERN,
    get_labels_from_ai_output,
    write_output,
)

_CATEGORY_PATTERN = re.compile(r'"category"\s*:\s*"([a-zA-Z0-9_-]+)"')


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Parse AI categorization output into validated labels and category.",
    )
    parser.add_argument(
        "--raw-output",
        default=os.environ.get("RAW_OUTPUT", ""),
        help="AI output containing labels and category JSON",
    )
    parser.add_argument(
        "--fallback-labels",
        default=os.environ.get("FALLBACK_LABELS", ""),
        help="Comma-separated fallback labels from composite action",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raw_output: str = args.raw_output
    fallback_labels: str = args.fallback_labels

    try:
        with open("/tmp/categorize-output.txt", "w", encoding="utf-8") as f:
            f.write(raw_output)
    except OSError:
        pass

    # Security: reject shell metacharacters
    labels = get_labels_from_ai_output(raw_output)

    if not labels and fallback_labels:
        labels = [
            item.strip()
            for item in fallback_labels.split(",")
            if item.strip() and SAFE_NAME_PATTERN.match(item.strip())
        ]

    category = "unknown"
    match = _CATEGORY_PATTERN.search(raw_output)
    if match:
        category = match.group(1)

    labels_json = json.dumps(labels)

    write_output("labels", labels_json)
    write_output("category", category)
    return 0


if __name__ == "__main__":
    sys.exit(main())
