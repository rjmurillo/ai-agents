"""Prepare conflict context for AI analysis.

Replaces the inline PowerShell block in pr-maintenance.yml (ADR-006).
Fetches and merges the PR branch to get conflict markers, then gathers
per-file context (conflict markers and recent git log for both branches).
Writes URL-percent-encoded conflict_context to GITHUB_OUTPUT and aborts
the merge.

EXIT CODES (ADR-035):
  0 - Success
  2 - Configuration error (GITHUB_OUTPUT not set)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

EXIT_SUCCESS = 0
EXIT_CONFIG = 2


def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
    )


def _git_log(ref: str, filepath: str) -> list[str]:
    result = _git(["log", "--oneline", "-5", ref, "--", filepath])
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return result.stdout.splitlines()


def _conflict_lines(filepath: str) -> list[str]:
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return []

    lines = []
    for line in content.splitlines():
        if line.startswith(("<<<<<<< ", "======= ", ">>>>>>> ")) or (
            line.startswith("<<<<<<<") or line.startswith("=======") or line.startswith(">>>>>>>")
        ):
            lines.append(line)
        else:
            lines.append(line)
        if len(lines) >= 100:
            break
    return lines


def build_context(blocked_files: list[str], base_ref: str) -> str:
    sections = []
    for filepath in blocked_files:
        section = [f"### File: {filepath}", ""]
        section += ["#### Conflict markers:", "```"]
        section += _conflict_lines(filepath)
        section += ["```", ""]
        section += ["#### Recent commits (PR branch):", "```"]
        section += _git_log("HEAD", filepath)
        section += ["```", ""]
        section += ["#### Recent commits (base branch):", "```"]
        section += _git_log(f"origin/{base_ref}", filepath)
        section += ["```", ""]
        sections.append("\n".join(section))
    return "\n".join(sections)


def main() -> int:
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    if not output_path:
        print("ERROR: GITHUB_OUTPUT not set", file=sys.stderr)
        return EXIT_CONFIG

    head_ref = os.environ.get("HEAD_REF", "")
    base_ref = os.environ.get("BASE_REF", "")
    blocked_files_json = os.environ.get("BLOCKED_FILES_JSON", "")

    try:
        blocked_files = json.loads(blocked_files_json) if blocked_files_json else []
        if not isinstance(blocked_files, list):
            blocked_files = []
    except json.JSONDecodeError:
        blocked_files = []

    # Fetch and merge to produce conflict markers.
    _git(["fetch", "origin", head_ref])
    _git(["checkout", head_ref])
    _git(["fetch", "origin", base_ref])
    _git(["merge", f"origin/{base_ref}"])

    context_str = build_context(blocked_files, base_ref)

    # Percent-encode for GHA output (%->%25 first, then newlines).
    encoded = context_str.replace("%", "%25").replace("\n", "%0A").replace("\r", "%0D")

    with open(output_path, "a", encoding="utf-8") as f:
        f.write(f"conflict_context={encoded}\n")

    # Abort the in-progress merge so subsequent steps start clean.
    _git(["merge", "--abort"])

    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
