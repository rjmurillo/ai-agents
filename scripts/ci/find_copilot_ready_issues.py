"""Find issues with the copilot-ready label.

Replaces the inline bash block in copilot-context-synthesis.yml
(ADR-006: no logic in YAML). Calls gh CLI to list open issues with the
copilot-ready label, then writes space-separated issue numbers and a
count to GITHUB_OUTPUT.

When gh CLI fails (e.g., no auth in a local test run), the script writes
count=0 to GITHUB_OUTPUT and exits 0, matching the original pipeline
behavior where `gh issue list | tr` would absorb a gh failure silently
(tr exits 0 on empty input). A WARNING is emitted to stderr so the
degradation is visible in CI logs.

EXIT CODES (ADR-035):
  0  - Success (includes zero-issues case and graceful gh degradation)
  2  - Configuration error (GITHUB_OUTPUT not set)
"""

from __future__ import annotations

import os
import subprocess
import sys

EXIT_SUCCESS = 0
EXIT_CONFIG = 2


def find_issues() -> tuple[list[str], int]:
    """Return (issue_number_list, returncode) from gh CLI."""
    result = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--label",
            "copilot-ready",
            "--state",
            "open",
            "--json",
            "number",
            "--jq",
            ".[].number",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return [], result.returncode

    numbers = result.stdout.strip().split() if result.stdout.strip() else []
    return numbers, 0


def main() -> int:
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    if not output_path:
        print("ERROR: GITHUB_OUTPUT not set", file=sys.stderr)
        return EXIT_CONFIG

    print("Searching for issues with copilot-ready label...")
    numbers, rc = find_issues()

    if rc != 0:
        print(
            f"WARNING: gh issue list failed (exit {rc}); treating as zero issues",
            file=sys.stderr,
        )
        numbers = []

    issues = " ".join(numbers)
    count = len(numbers)

    with open(output_path, "a", encoding="utf-8") as f:
        f.write(f"issues={issues}\n")
        f.write(f"count={count}\n")

    if count == 0:
        print("No issues found with copilot-ready label")
    else:
        print(f"Found {count} issue(s) to process: {issues}")

    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
