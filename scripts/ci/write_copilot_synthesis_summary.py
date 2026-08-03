#!/usr/bin/env python3
"""Write the Copilot context synthesis job summary to GITHUB_STEP_SUMMARY.

Reads ISSUE_NUMBER from the environment and writes a markdown summary
to $GITHUB_STEP_SUMMARY.
Replaces the inline "Summary" run step in copilot-context-synthesis.yml
(issue #2967, ADR-006 burn-down).

EXIT CODES (ADR-035):
  0  - Summary written to GITHUB_STEP_SUMMARY, or printed to stdout when unset
  2  - Usage error (ISSUE_NUMBER not set)
"""

from __future__ import annotations

import os
import sys

EXIT_OK = 0
EXIT_USAGE = 2


def _build_summary(issue_number: str) -> str:
    return (
        "## Copilot Context Synthesis Complete :robot:\n"
        "\n"
        f"**Issue**: #{issue_number}\n"
        "\n"
        "### Actions Taken\n"
        "- Synthesized context from trusted sources\n"
        "- Posted/updated synthesis comment with @copilot mention\n"
        "- Assigned copilot-swe-agent to the issue\n"
        "- Removed copilot-ready label (processing complete)\n"
        "\n"
        "Copilot will now create a PR based on the synthesized context.\n"
    )


def main() -> int:
    issue_number = os.environ.get("ISSUE_NUMBER", "").strip()
    if not issue_number:
        print("ERROR: ISSUE_NUMBER is not set", file=sys.stderr)
        return EXIT_USAGE

    summary = _build_summary(issue_number)
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(summary)
    else:
        print(summary, end="")

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
