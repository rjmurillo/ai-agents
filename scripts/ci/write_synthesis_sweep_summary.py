"""Write the Copilot Context Synthesis Sweep step summary.

Replaces the inline bash block in copilot-context-synthesis.yml
(ADR-006: no logic in YAML). Reads trigger, count, and issues from env
vars and appends a markdown summary to GITHUB_STEP_SUMMARY.

EXIT CODES (ADR-035):
  0  - Success
  2  - Configuration error (GITHUB_STEP_SUMMARY not set)
"""

from __future__ import annotations

import os
import sys

EXIT_SUCCESS = 0
EXIT_CONFIG = 2


def build_sweep_summary(trigger: str, count: int, issues: str) -> str:
    lines = [
        "## Copilot Context Synthesis Sweep :broom:",
        "",
        f"**Trigger**: {trigger}",
        f"**Issues Found**: {count}",
        "",
    ]

    if count == 0:
        lines.append(
            "No issues with `copilot-ready` label found. All caught up! :white_check_mark:"
        )
    else:
        lines.extend(
            [
                "### Issues Processed",
                f"Issues: {issues}",
                "",
                "Check the job logs for individual issue processing results.",
            ]
        )

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not summary_path:
        print("ERROR: GITHUB_STEP_SUMMARY not set", file=sys.stderr)
        return EXIT_CONFIG

    trigger = os.environ.get("TRIGGER", "unknown")
    issues_count_str = os.environ.get("ISSUES_COUNT", "0")
    issues = os.environ.get("ISSUES", "")

    try:
        issues_count = int(issues_count_str)
    except ValueError:
        issues_count = 0

    content = build_sweep_summary(trigger, issues_count, issues)

    try:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(content)
    except OSError as exc:
        print(f"ERROR: cannot write to {summary_path}: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
