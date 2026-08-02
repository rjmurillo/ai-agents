#!/usr/bin/env python3
"""Write drift detection summary to GITHUB_STEP_SUMMARY.

Replaces the inline shell in drift-detection.yml (ADR-006):

    if [ "${{ steps.drift.outputs.drift_detected }}" == "true" ]; then ...

ENV:
  DRIFT_DETECTED       - "true" or "false" (from step output)
  GITHUB_STEP_SUMMARY  - path to the step summary file

EXIT CODES (ADR-035):
  0 - summary written
"""

from __future__ import annotations

import os
import sys

EXIT_OK = 0


def build_summary(drift_detected: str) -> str:
    """Return the markdown summary string."""
    lines = ["## Drift Detection Summary", ""]
    if drift_detected == "true":
        lines += [
            ":warning: **Drift detected** in Claude agents",
            "",
            "See the created/updated GitHub issue for details.",
        ]
    else:
        lines.append(
            ":white_check_mark: **No new drift**"
            " - every compared pair scored at or above the similarity"
            " threshold, or stayed at or above a recorded baseline floor."
            " Baselined pairs are still drifted; they are tracked, not in sync."
        )
    lines += [
        "",
        "### Pairs Compared",
        "- `src/claude/` vs `src/vs-code-agents/`",
        "- `.claude/agents/` vs `.github/agents/`,"
        + " scoped to agents whose prose comes from `templates/agents/`",
    ]
    return "\n".join(lines) + "\n"


def run(_argv: list[str] | None = None) -> int:
    """Write the summary."""
    drift_detected = os.environ.get("DRIFT_DETECTED", "false")
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY", "")
    content = build_summary(drift_detected)
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(content)
    else:
        print(content, end="")
    return EXIT_OK


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
