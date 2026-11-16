"""The gh steps of close_pr.py: read the comment, read the PR state, post, close.

Each step maps its failure to an ADR-035 exit code through ``error_and_exit``.
"""

from __future__ import annotations

import json
import os
import subprocess

from github_core.api import error_and_exit
from github_core.not_found import is_pr_not_found
from github_core.validation import assert_valid_body_file, read_body_file_text


def read_comment(comment: str, comment_file: str) -> str:
    """Return the closing comment text from --comment or --comment-file."""
    if not comment_file:
        return comment
    if not os.path.isfile(comment_file):
        error_and_exit(f"Comment file not found: {comment_file}", 2)
    assert_valid_body_file(comment_file)
    try:
        return read_body_file_text(comment_file, allow_git_dir=True)
    except (OSError, ValueError) as exc:
        error_and_exit(f"Failed to read comment file {comment_file}: {exc}", 2)


def pr_state(pr: int, repo_flag: str) -> str:
    """Read the PR state, or exit 2/3 the same way main previously did."""
    state_result = subprocess.run(
        ["gh", "pr", "view", str(pr), "--repo", repo_flag, "--json", "state"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if state_result.returncode != 0:
        output = state_result.stderr or state_result.stdout
        if is_pr_not_found(output):
            error_and_exit(f"PR #{pr} not found in {repo_flag}", 2)
        error_and_exit(f"Failed to get PR state: {output}", 3)

    return json.loads(state_result.stdout).get("state", "")


def post_closing_comment(pr: int, repo_flag: str, comment: str) -> None:
    """Post the closing comment, or exit 3 without closing the PR."""
    comment_result = subprocess.run(
        ["gh", "pr", "comment", str(pr), "--repo", repo_flag, "--body", comment],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if comment_result.returncode != 0:
        error_and_exit(
            f"Failed to post the closing comment on PR #{pr}: "
            f"{comment_result.stderr or comment_result.stdout}. "
            "The PR was NOT closed, so the explanation is never lost. "
            "Retry the same command once the API error clears.",
            3,
        )


def close_pull_request(pr: int, repo_flag: str) -> None:
    """Close the PR, or exit 3 on failure."""
    close_result = subprocess.run(
        ["gh", "pr", "close", str(pr), "--repo", repo_flag],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if close_result.returncode != 0:
        error_and_exit(
            f"Failed to close PR #{pr}: {close_result.stderr or close_result.stdout}",
            3,
        )
