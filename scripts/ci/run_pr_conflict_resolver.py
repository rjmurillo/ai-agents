"""Auto-resolve PR conflicts by calling resolve_pr_conflicts.py.

Replaces the inline PowerShell block in pr-maintenance.yml (ADR-006).
Calls .claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py,
parses its JSON output, and writes needs_ai and blocked_files to
GITHUB_OUTPUT.

EXIT CODES (ADR-035):
  0 - Success (includes both auto-resolved and needs_ai cases)
  1 - Resolver failed with a non-expected exit code (>1)
  2 - Configuration error (GITHUB_OUTPUT not set)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_CONFIG = 2

_RESOLVER = ".claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py"


def main() -> int:
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    if not output_path:
        print("ERROR: GITHUB_OUTPUT not set", file=sys.stderr)
        return EXIT_CONFIG

    pr_number = os.environ.get("PR_NUMBER", "")
    head_ref = os.environ.get("HEAD_REF", "")
    base_ref = os.environ.get("BASE_REF", "")
    repo_owner = os.environ.get("REPO_OWNER", "")
    repo_name = os.environ.get("REPO_NAME", "")

    print(f"Attempting auto-resolution for PR #{pr_number}")
    print(f"Branch: {head_ref} -> {base_ref}")

    result = subprocess.run(
        [
            "python3",
            _RESOLVER,
            "--owner",
            repo_owner,
            "--repo",
            repo_name,
            "--pr-number",
            pr_number,
            "--branch-name",
            head_ref,
            "--target-branch",
            base_ref,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    # Resolver exit contract: 0=all resolved, 1=some blocked (both valid JSON).
    # Exit 2/3/4 = fatal per ADR-035; propagate the category so callers can distinguish.
    if result.returncode > 1:
        msg = (
            f"::error::PR #{pr_number}: resolver failed (exit {result.returncode}): {result.stdout}"
        )
        print(msg, file=sys.stderr)
        return result.returncode

    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(
            f"::error::PR #{pr_number}: resolver output is not valid JSON: {exc}",
            file=sys.stderr,
        )
        return EXIT_FAILURE

    with open(output_path, "a", encoding="utf-8") as f:
        if parsed.get("success"):
            resolved_count = len(parsed.get("files_resolved", []))
            print(f"::notice::PR #{pr_number}: Auto-resolved - {resolved_count} file(s)")
            f.write("needs_ai=false\n")
        else:
            blocked = parsed.get("files_blocked", [])
            print(f"::warning::PR #{pr_number}: Auto-resolution blocked on: {', '.join(blocked)}")
            f.write("needs_ai=true\n")
            f.write(f"blocked_files={json.dumps(blocked, separators=(',', ':'))}\n")

    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
