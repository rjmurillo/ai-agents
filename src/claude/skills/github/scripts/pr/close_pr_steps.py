"""The gh steps of close_pr.py: read the comment, read the PR state, post, close.

Each step maps its failure to an ADR-035 exit code through ``error_and_exit``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import error_and_exit
from github_core.not_found import is_pr_not_found
from github_core.validation import assert_valid_body_file, read_body_file_text


def _run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one gh command with captured, UTF-8 decoded output and a 30s timeout."""
    return subprocess.run(
        args,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


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
    """Read the PR state, or exit 2/3 as ADR-035 defines."""
    state_result = _run_gh(["gh", "pr", "view", str(pr), "--repo", repo_flag, "--json", "state"])

    if state_result.returncode != 0:
        output = state_result.stderr or state_result.stdout
        if is_pr_not_found(output):
            error_and_exit(f"PR #{pr} not found in {repo_flag}", 2)
        error_and_exit(f"Failed to get PR state: {output}", 3)

    return json.loads(state_result.stdout).get("state", "")


def post_closing_comment(pr: int, repo_flag: str, comment: str) -> None:
    """Post the closing comment, or exit 3 without closing the PR."""
    comment_result = _run_gh(
        ["gh", "pr", "comment", str(pr), "--repo", repo_flag, "--body", comment]
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
    close_result = _run_gh(["gh", "pr", "close", str(pr), "--repo", repo_flag])

    if close_result.returncode != 0:
        error_and_exit(
            f"Failed to close PR #{pr}: {close_result.stderr or close_result.stdout}",
            3,
        )
