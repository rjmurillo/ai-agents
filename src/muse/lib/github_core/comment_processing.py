"""Shared reactions and messages for the existing PR comment processors."""

from __future__ import annotations

import subprocess
import sys
from typing import Any


def add_comment_reaction(owner: str, repo: str, comment_id: int, reaction: str = "eyes") -> bool:
    """Try review comments before falling back to issue comments."""
    for kind in ("pulls", "issues"):
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{owner}/{repo}/{kind}/comments/{comment_id}/reactions",
                "-X",
                "POST",
                "-f",
                f"content={reaction}",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode == 0:
            print(f"Added {reaction} reaction to comment {comment_id}")
            return True
    error_str = result.stderr.strip() or result.stdout.strip()
    print(
        f"WARNING: Failed to add reaction to comment {comment_id}: {error_str}",
        file=sys.stderr,
    )
    return False


def format_wontfix_reply(resolution: str) -> str:
    return (
        "Thank you for the feedback. After review, "
        "we've decided not to implement this change:\n\n"
        f"{resolution}"
    )


def report_comment_action(classification: str, comment: dict[str, Any]) -> None:
    if classification == "stale":
        print("  Stale comment needs manual resolution (thread ID required)")
    elif classification == "question":
        print(f"  Needs human response: {comment.get('summary', '')}")
    elif classification in ("quick-fix", "standard", "strategic"):
        print(f"  Action needed: {comment.get('action', '')} - {comment.get('summary', '')}")
    else:
        print(f"  Unknown classification '{classification}', skipping")
