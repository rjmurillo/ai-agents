"""Write PR discovery summary to GITHUB_STEP_SUMMARY.

Replaces the inline PowerShell block in pr-maintenance.yml (ADR-006).
Reads SUMMARY_JSON from the environment, builds a markdown summary,
and appends it to GITHUB_STEP_SUMMARY.

EXIT CODES (ADR-035):
  0 - Success
  2 - Configuration error (GITHUB_STEP_SUMMARY not set)
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

EXIT_SUCCESS = 0
EXIT_CONFIG = 2


def build_summary(parsed: dict[str, Any]) -> str:
    summary_stats = parsed.get("summary", {})
    lines = [
        "## PR Discovery Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Open PRs Scanned | {summary_stats.get('total', 0)} |",
        f"| PRs Need Action | {summary_stats.get('actionRequired', 0)} |",
        f"| Blocked (human) | {summary_stats.get('blocked', 0)} |",
        f"| Derivative PRs | {summary_stats.get('derivatives', 0)} |",
        "",
    ]

    prs = parsed.get("prs", [])
    if prs:
        lines += [
            "",
            "### PRs Requiring Action",
            "",
            "| PR | Category | Reason | Has Conflicts |",
            "|----|----------|--------|---------------|",
        ]
        for pr in prs:
            conflict_icon = ":warning:" if pr.get("hasConflicts") else ":white_check_mark:"
            num = pr.get("number", "")
            cat = pr.get("category", "")
            reason = pr.get("reason", "")
            lines.append(f"| #{num} | {cat} | {reason} | {conflict_icon} |")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not summary_path:
        print("ERROR: GITHUB_STEP_SUMMARY not set", file=sys.stderr)
        return EXIT_CONFIG

    summary_json = os.environ.get("SUMMARY_JSON", "").strip()

    try:
        parsed = json.loads(summary_json) if summary_json else {}
    except json.JSONDecodeError:
        parsed = {}

    output = build_summary(parsed)

    with open(summary_path, "a", encoding="utf-8") as f:
        f.write(output)

    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
