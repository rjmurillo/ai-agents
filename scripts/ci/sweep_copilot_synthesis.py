"""Process all issues with the copilot-ready label in a sweep.

Replaces the inline PowerShell block in copilot-context-synthesis.yml
(ADR-006: no logic in YAML). Iterates over all issue numbers in ISSUES,
calls invoke_copilot_assignment.py for each, removes the copilot-ready
label on success. Job-level failure is suppressed so as many issues as
possible are processed.

EXIT CODES (ADR-035):
  0  - Success (partial failures are logged as warnings, not step failures)
  2  - (reserved; env error never raised since empty ISSUES is valid)
"""

from __future__ import annotations

import os
import subprocess
import sys

EXIT_SUCCESS = 0

_SYNTHESIS_SCRIPT = ".claude/skills/github/scripts/issue/invoke_copilot_assignment.py"


def _process_issue(issue_number: str) -> bool:
    """Synthesize context for one issue. Returns True on success."""
    print(f"\n=== Processing Issue #{issue_number} ===")
    sys.stdout.flush()
    result = subprocess.run(
        [sys.executable, _SYNTHESIS_SCRIPT, "--issue-number", issue_number],
    )
    if result.returncode != 0:
        print(f"::warning::Issue #{issue_number} - Synthesis failed (exit {result.returncode})")
        return False

    print(f"::notice::Issue #{issue_number} - synthesized context")

    gh_result = subprocess.run(
        ["gh", "issue", "edit", issue_number, "--remove-label", "copilot-ready"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if gh_result.returncode == 0:
        print(f"::notice::Issue #{issue_number} - Removed copilot-ready label")
    else:
        print(f"::warning::Issue #{issue_number} - Failed to remove label: {gh_result.stderr}")

    return True


def main() -> int:
    issues_str = os.environ.get("ISSUES", "").strip()
    if not issues_str:
        print("No issues to process")
        return EXIT_SUCCESS

    issues = [n for n in issues_str.split() if n]
    if not issues:
        print("No issues to process")
        return EXIT_SUCCESS

    print(f"Processing {len(issues)} issue(s)...")

    failed: list[str] = []
    for issue_number in issues:
        if not _process_issue(issue_number):
            failed.append(issue_number)

    print("\n=== Sweep Complete ===")
    print(f"Processed: {len(issues) - len(failed)} issue(s)")
    if failed:
        print(f"Failed: {len(failed)} issue(s): {', '.join(failed)}")

    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
