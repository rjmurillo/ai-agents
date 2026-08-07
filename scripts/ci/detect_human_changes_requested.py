"""Detect human CHANGES_REQUESTED reviews on a PR.

Replaces the inline PowerShell block in pr-maintenance.yml (ADR-006).
Calls gh to fetch PR reviews, filters out known bot authors, and writes
human_changes_requested=true/false to GITHUB_OUTPUT.

EXIT CODES (ADR-035):
  0 - Success (includes gh failure gracefully handled as false)
  2 - Configuration error (GITHUB_OUTPUT not set)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

EXIT_SUCCESS = 0
EXIT_CONFIG = 2

_BOT_AUTHORS = frozenset(
    [
        "coderabbitai[bot]",
        "github-actions[bot]",
        "copilot-swe-agent[bot]",
        "gemini-code-assist[bot]",
        "rjmurillo-bot",
    ]
)


def main() -> int:
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    if not output_path:
        print("ERROR: GITHUB_OUTPUT not set", file=sys.stderr)
        return EXIT_CONFIG

    pr_number = os.environ.get("PR_NUMBER", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")

    result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            pr_number,
            "--repo",
            repo,
            "--json",
            "reviews",
            "--jq",
            "{reviews: .reviews}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        print(
            "::warning::Failed to fetch PR review data; proceeding without human-changes detection"
        )
        with open(output_path, "a", encoding="utf-8") as f:
            f.write("human_changes_requested=false\n")
        return EXIT_SUCCESS

    try:
        pr_data = json.loads(result.stdout)
    except json.JSONDecodeError:
        pr_data = {}

    reviews = pr_data.get("reviews", [])
    human_changes = [
        r
        for r in reviews
        if r.get("state") == "CHANGES_REQUESTED"
        and r.get("author", {}).get("login", "") not in _BOT_AUTHORS
    ]

    with open(output_path, "a", encoding="utf-8") as f:
        if human_changes:
            print(
                f"::warning::PR #{pr_number}: Human CHANGES_REQUESTED present; "
                "bot will still respond, but flagging for visibility"
            )
            f.write("human_changes_requested=true\n")
        else:
            f.write("human_changes_requested=false\n")

    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
