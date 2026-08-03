"""Find issues with the copilot-ready label.

Replaces the inline bash block in copilot-context-synthesis.yml
(ADR-006: no logic in YAML). Calls gh CLI to list open issues with the
copilot-ready label, then writes space-separated issue numbers and a
count to GITHUB_OUTPUT.

EXIT CODES (ADR-035):
  0  - Success (includes zero-issues case)
  1  - gh CLI failure
  2  - Configuration error (GITHUB_OUTPUT not set)
"""

from __future__ import annotations

import os
import subprocess
import sys

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_CONFIG = 2


def find_issues() -> tuple[list[str], int, str]:
    """Return (issue_number_list, returncode, stderr) from gh CLI."""
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
        errors="replace",
    )
    if result.returncode != 0:
        return [], result.returncode, result.stderr or ""

    numbers = result.stdout.strip().split() if result.stdout.strip() else []
    return numbers, 0, ""


def main() -> int:
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    if not output_path:
        print("ERROR: GITHUB_OUTPUT not set", file=sys.stderr)
        return EXIT_CONFIG

    print("Searching for issues with copilot-ready label...")
    numbers, rc, stderr = find_issues()

    if rc != 0:
        safe = stderr.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(
            f"::error::gh issue list failed (exit {rc}): {safe}",
            file=sys.stderr,
        )
        return EXIT_FAILURE

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
