#!/usr/bin/env python3
"""Parse AI categorization output into validated labels and category.

Replaces the inline PowerShell block in the 'Parse Categorization Results'
step (id: parse-categorize) of ai-issue-triage.yml.

Input env vars:
    RAW_OUTPUT         - AI output containing labels and category JSON
    FALLBACK_LABELS    - Comma-separated fallback labels from composite action
    GITHUB_OUTPUT      - Path to GitHub Actions output file
    GITHUB_WORKSPACE   - Workspace root (for package imports)
"""

from __future__ import annotations

import json
import os
import re
import sys

# Add workspace root to Python path for package imports
workspace = os.environ.get("GITHUB_WORKSPACE", ".")
sys.path.insert(0, workspace)

from scripts.ai_review_common import get_labels_from_ai_output

_SAFE_NAME = re.compile(
    r"^(?=.{1,50}$)[A-Za-z0-9](?:[A-Za-z0-9 _.\-]*[A-Za-z0-9])?$"
)

_CATEGORY_PATTERN = re.compile(r'"category"\s*:\s*"([a-zA-Z0-9_-]+)"')


def write_output(key: str, value: str) -> None:
    """Append a key=value line to the GitHub Actions output file."""
    output_file = os.environ.get("GITHUB_OUTPUT", "")
    if output_file:
        with open(output_file, "a") as f:
            f.write(f"{key}={value}\n")


def main() -> None:
    raw_output = os.environ.get("RAW_OUTPUT", "")
    fallback_labels = os.environ.get("FALLBACK_LABELS", "")

    # Save output for debugging
    with open("/tmp/categorize-output.txt", "w", encoding="utf-8") as f:
        f.write(raw_output)

    # Parse labels with hardened function (rejects shell metacharacters)
    labels = get_labels_from_ai_output(raw_output)

    # Fallback to composite action output if needed
    if not labels and fallback_labels:
        labels = [
            item.strip()
            for item in fallback_labels.split(",")
            if item.strip() and _SAFE_NAME.match(item.strip())
        ]

    # Parse category with validation (alphanumeric, underscore, hyphen only)
    category = "unknown"
    match = _CATEGORY_PATTERN.search(raw_output)
    if match:
        category = match.group(1)

    # Output as JSON array for safe consumption
    labels_json = json.dumps(labels)

    write_output("labels", labels_json)
    write_output("category", category)


if __name__ == "__main__":
    main()
