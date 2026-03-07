"""Git repository information helpers.

Provides functions to extract git state for session initialization.
Retrieves repository root, current branch, commit SHA, and working tree status.
"""

from __future__ import annotations

import subprocess

from .common_types import ApplicationFailedError


def _run_git(*args: str) -> str:
    """Run a git command and return stripped stdout.

    Raises:
        RuntimeError: Git command failed with non-zero exit code.
    """
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        msg = f"Git command 'git {' '.join(args)}' failed (exit {result.returncode}): {detail}"
        raise RuntimeError(msg)
    return result.stdout.strip()


def get_git_info() -> dict[str, str]:
    """Gather git repository information for session initialization.

    Returns a dict with keys:
        repo_root: Absolute path to repository root
        branch: Current branch name (empty string for detached HEAD)
        commit: Short commit SHA
        status: 'clean' if no changes, 'dirty' if working tree has changes

    Raises:
        RuntimeError: Not in a git repository or git operations failed.
        ApplicationFailedError: Unexpected errors during git command execution.
    """
    try:
        repo_root = _run_git("rev-parse", "--show-toplevel") or ""

        try:
            branch = _run_git("branch", "--show-current")
        except RuntimeError:
            branch = ""

        commit = _run_git("rev-parse", "--short", "HEAD")

        status_output = _run_git("status", "--short")
        git_status = "clean" if not status_output else "dirty"

        return {
            "repo_root": repo_root,
            "branch": branch,
            "commit": commit,
            "status": git_status,
        }
    except RuntimeError:
        raise
    except Exception as exc:
        msg = (
            f"UNEXPECTED ERROR in get_git_info\n"
            f"Exception Type: {type(exc).__name__}\n"
            f"Message: {exc}\n\n"
            f"This is a bug. Please report this error with the above details."
        )
        raise ApplicationFailedError(msg) from exc
