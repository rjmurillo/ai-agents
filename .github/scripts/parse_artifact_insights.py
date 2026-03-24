#!/usr/bin/env python3
"""Parse AI artifact insight output into structured findings for issue creation.

Input env vars:
    RAW_OUTPUT         - AI output containing FINDING blocks
    PRIORITY_THRESHOLD - Minimum priority to include (P0, P1, P2, P3)
    GITHUB_OUTPUT      - Path to GitHub Actions output file
    GITHUB_WORKSPACE   - Workspace root (for package imports)

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Config error
    3 - External error
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass

workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
sys.path.insert(0, workspace)

from scripts.ai_review_common import (  # noqa: E402
    SAFE_NAME_PATTERN,
    write_output,
)

# Priority ordering for threshold comparison
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

# Valid finding types
VALID_TYPES = {"TODO", "LESSON", "BLOCKED", "IMPROVEMENT", "FOLLOWUP"}

# Allowed labels (must match repository labels)
ALLOWED_LABELS = {
    "enhancement",
    "bug",
    "documentation",
    "automation",
    "area-workflows",
    "area-prompts",
    "area-infrastructure",
    "area-installation",
}


@dataclass
class Finding:
    """Structured finding from artifact scan."""

    finding_type: str
    title: str
    body: str
    priority: str
    labels: list[str]
    source: str


def parse_finding_block(block: str) -> Finding | None:
    """Parse a single FINDING block into a structured Finding.

    Args:
        block: Text between FINDING: and ---

    Returns:
        Finding object or None if parsing fails
    """
    lines = block.strip().split("\n")

    data: dict[str, str] = {}
    current_key: str | None = None
    current_value: list[str] = []

    for line in lines:
        # Check for key: value pattern
        match = re.match(r"^(TYPE|TITLE|BODY|PRIORITY|LABELS|SOURCE):\s*(.*)$", line)
        if match:
            # Save previous key if exists
            if current_key:
                data[current_key] = " ".join(current_value).strip()

            current_key = match.group(1)
            current_value = [match.group(2)]
        elif current_key:
            # Continuation of previous value
            current_value.append(line.strip())

    # Save last key
    if current_key:
        data[current_key] = " ".join(current_value).strip()

    # Validate required fields
    required = ["TYPE", "TITLE", "BODY", "PRIORITY", "LABELS", "SOURCE"]
    for field in required:
        if field not in data:
            print(f"Missing required field: {field}", file=sys.stderr)
            return None

    # Validate type
    finding_type = data["TYPE"].upper()
    if finding_type not in VALID_TYPES:
        print(f"Invalid finding type: {finding_type}", file=sys.stderr)
        return None

    # Validate priority
    priority = data["PRIORITY"].upper()
    if priority not in PRIORITY_ORDER:
        print(f"Invalid priority: {priority}", file=sys.stderr)
        return None

    # Validate and filter labels
    raw_labels = [label.strip() for label in data["LABELS"].split(",")]
    labels = [
        label for label in raw_labels if label in ALLOWED_LABELS and SAFE_NAME_PATTERN.match(label)
    ]

    # Validate title (security: reject shell metacharacters)
    title = data["TITLE"]
    if not title or len(title) > 200:
        print(f"Invalid title length: {len(title)}", file=sys.stderr)
        return None

    # Sanitize title (allow-list: only conventional commit title characters)
    title = re.sub(r"[^a-zA-Z0-9\s\-\(\):.,/]", "", title)

    return Finding(
        finding_type=finding_type,
        title=title,
        body=data["BODY"],
        priority=priority,
        labels=labels,
        source=data["SOURCE"],
    )


def parse_findings(raw_output: str) -> list[Finding]:
    """Parse all FINDING blocks from AI output.

    Args:
        raw_output: Full AI output text

    Returns:
        List of parsed Finding objects
    """
    findings: list[Finding] = []

    # Split on FINDING: markers
    blocks = re.split(r"FINDING:\s*\n?", raw_output)

    for block in blocks[1:]:  # Skip text before first FINDING:
        # Find the end marker
        end_match = re.search(r"---", block)
        if end_match:
            block = block[: end_match.start()]

        finding = parse_finding_block(block)
        if finding:
            findings.append(finding)

    return findings


def filter_by_priority(findings: list[Finding], threshold: str) -> list[Finding]:
    """Filter findings by priority threshold.

    Args:
        findings: List of findings
        threshold: Minimum priority (P0, P1, P2, P3)

    Returns:
        Filtered list including only findings at or above threshold
    """
    threshold_value = PRIORITY_ORDER.get(threshold, 2)

    return [f for f in findings if PRIORITY_ORDER.get(f.priority, 3) <= threshold_value]


def findings_to_json(findings: list[Finding]) -> str:
    """Convert findings to JSON for PowerShell consumption.

    Args:
        findings: List of Finding objects

    Returns:
        JSON string representation
    """
    return json.dumps(
        [
            {
                "type": f.finding_type,
                "title": f.title,
                "body": f.body,
                "priority": f.priority,
                "labels": f.labels,
                "source": f.source,
            }
            for f in findings
        ]
    )


def main() -> int:
    """Entry point."""
    raw_output = os.environ.get("RAW_OUTPUT", "")
    priority_threshold = os.environ.get("PRIORITY_THRESHOLD", "P2").upper()

    if priority_threshold not in PRIORITY_ORDER:
        print(f"Invalid priority threshold: {priority_threshold}", file=sys.stderr)
        priority_threshold = "P2"

    # Parse findings
    findings = parse_findings(raw_output)
    print(f"Parsed {len(findings)} findings from AI output")

    # Filter by priority
    filtered = filter_by_priority(findings, priority_threshold)
    print(f"Filtered to {len(filtered)} findings at {priority_threshold} or higher")

    # Convert to JSON
    findings_json = findings_to_json(filtered)

    # Write outputs
    write_output("finding_count", str(len(filtered)))
    write_output("findings_json", findings_json)

    # Also write summary
    if filtered:
        print("\nFindings summary:")
        for f in filtered:
            print(f"  [{f.priority}] {f.finding_type}: {f.title}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
