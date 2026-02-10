#!/usr/bin/env python3
"""Parse AI roadmap alignment output into milestone, priority, and escalation fields.

Input env vars:
    RAW_OUTPUT            - AI output with milestone, priority, escalation data
    MILESTONE_FROM_ACTION - Fallback milestone from composite action output
    GITHUB_OUTPUT         - Path to GitHub Actions output file
    GITHUB_WORKSPACE      - Workspace root (for package imports)
"""

from __future__ import annotations

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
    get_milestone_from_ai_output,
    write_output,
)

_PRIORITY_PATTERN = re.compile(r'"priority"\s*:\s*"(P[0-4])"')
_ESCALATE_PATTERN = re.compile(r'"escalate_to_prd"\s*:\s*(true|false)')
_COMPLEXITY_PATTERN = re.compile(r'"complexity_score"\s*:\s*(\d{1,2})')
_CRITERIA_PATTERN = re.compile(r'"escalation_criteria"\s*:\s*\[([^\]]*)\]')


def main() -> None:
    raw_output = os.environ.get("RAW_OUTPUT", "")
    milestone_from_action = os.environ.get("MILESTONE_FROM_ACTION", "")

    try:
        with open("/tmp/align-output.txt", "w", encoding="utf-8") as f:
            f.write(raw_output)
    except OSError:
        pass

    milestone = get_milestone_from_ai_output(raw_output) or ""

    if not milestone and milestone_from_action:
        if SAFE_NAME_PATTERN.match(milestone_from_action):
            milestone = milestone_from_action

    priority = "P2"
    match = _PRIORITY_PATTERN.search(raw_output)
    if match:
        priority = match.group(1)

    escalate_to_prd = "false"
    match = _ESCALATE_PATTERN.search(raw_output)
    if match:
        escalate_to_prd = match.group(1)

    complexity_score = 0
    match = _COMPLEXITY_PATTERN.search(raw_output)
    if match:
        complexity_score = min(int(match.group(1)), 12)

    # Security: reject shell metacharacters
    escalation_criteria = ""
    match = _CRITERIA_PATTERN.search(raw_output)
    if match:
        criteria = [
            item.strip().strip('"').strip("'")
            for item in match.group(1).split(",")
        ]
        valid_criteria = [c for c in criteria if c and SAFE_NAME_PATTERN.match(c)]
        escalation_criteria = ",".join(valid_criteria)

    write_output("milestone", milestone)
    write_output("priority", priority)
    write_output("escalate_to_prd", escalate_to_prd)
    write_output("complexity_score", str(complexity_score))
    write_output("escalation_criteria", escalation_criteria)


if __name__ == "__main__":
    main()
