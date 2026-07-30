"""Run Copilot context synthesis for a single issue.

Replaces the inline PowerShell block in copilot-context-synthesis.yml
(ADR-006: no logic in YAML). Calls invoke_copilot_assignment.py with
the issue number from ISSUE_NUMBER and maps its exit code to step status.

EXIT CODES (ADR-035):
  0  - Success
  1  - Synthesis failed (logic error or assignment failure)
  2  - Configuration error (missing or invalid env var)
"""

from __future__ import annotations

import os
import subprocess
import sys

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_CONFIG = 2

_SYNTHESIS_SCRIPT = ".claude/skills/github/scripts/issue/invoke_copilot_assignment.py"


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001
    issue_number = os.environ.get("ISSUE_NUMBER", "").strip()
    if not issue_number:
        print("ERROR: ISSUE_NUMBER not set", file=sys.stderr)
        return EXIT_CONFIG

    try:
        int(issue_number)
    except ValueError:
        print(f"ERROR: ISSUE_NUMBER must be an integer, got: {issue_number!r}", file=sys.stderr)
        return EXIT_CONFIG

    print(f"Starting context synthesis for issue #{issue_number}")
    result = subprocess.run(
        [sys.executable, _SYNTHESIS_SCRIPT, "--issue-number", issue_number],
    )
    if result.returncode != 0:
        print(
            f"::error::Failed to synthesize context for issue #{issue_number}"
            f" (exit {result.returncode})",
            file=sys.stderr,
        )
        return EXIT_FAILURE

    print(f"::notice::Synthesized context for issue #{issue_number}")
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
