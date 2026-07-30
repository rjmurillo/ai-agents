"""Write final PR maintenance summary to GITHUB_STEP_SUMMARY.

Replaces the inline PowerShell block in pr-maintenance.yml (ADR-006).
Reads SUMMARY_JSON from the environment (routed through env to avoid
expression interpolation of PR-controlled content), finds agent-controlled
PRs, and appends a Next Steps table to GITHUB_STEP_SUMMARY.

EXIT CODES (ADR-035):
  0 - Success (includes "nothing to write" cases)
  2 - Configuration error (GITHUB_STEP_SUMMARY not set)
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

EXIT_SUCCESS = 0
EXIT_CONFIG = 2


def build_next_steps(action_required: list[dict[str, Any]]) -> str:
    pr_numbers = ", ".join(f"#{pr['number']}" for pr in action_required)
    numbers_csv = ",".join(str(pr["number"]) for pr in action_required)
    print(f"::notice::Action required for PRs: {pr_numbers}")
    print(f"Run: /pr-review {numbers_csv}")

    lines = [
        "",
        "---",
        "### Next Steps",
        "",
        "The following PRs require manual review via `/pr-review`:",
        "",
        "| PR | Reason | Action |",
        "|----|--------|--------|",
    ]
    for pr in action_required:
        num = pr.get("number", "")
        reason = pr.get("reason", "")
        lines.append(f"| #{num} | {reason} | `/pr-review {num}` |")
    return "\n".join(lines) + "\n"


def main() -> int:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not summary_path:
        print("ERROR: GITHUB_STEP_SUMMARY not set", file=sys.stderr)
        return EXIT_CONFIG

    summary_json = os.environ.get("SUMMARY_JSON", "").strip()

    if not summary_json:
        print("No discovery results available")
        return EXIT_SUCCESS

    try:
        parsed = json.loads(summary_json)
    except json.JSONDecodeError:
        print("No discovery results available")
        return EXIT_SUCCESS

    prs = parsed.get("prs", []) if isinstance(parsed, dict) else []
    action_required = [pr for pr in prs if pr.get("category") == "agent-controlled"]

    if not action_required:
        return EXIT_SUCCESS

    output = build_next_steps(action_required)
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write(output)

    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
