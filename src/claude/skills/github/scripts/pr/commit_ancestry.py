"""Classify a commit SHA against a pull request head in a local clone.

Split out of check_review_thread_resolution_shas.py to keep that script under
the 500-line taste limit. Stdlib only, so it runs under bare python3.
"""

from __future__ import annotations

import subprocess

_GIT_TIMEOUT_SECONDS = 30


def _git(repo_path: str, *args: str) -> tuple[int, str, str]:
    """Run git; a timeout or a git that cannot start returns rc -1 and the reason."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return -1, "", f"git {args[0]} timed out after {_GIT_TIMEOUT_SECONDS}s"
    except OSError as exc:
        return -1, "", f"git could not run: {exc}"
    return result.returncode, result.stdout, result.stderr


def _git_error(stderr: str) -> str:
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    return f"git-error: {lines[0]}" if lines else "git-error"


def _classify_unresolved(sha: str, repo_path: str) -> tuple[bool, str, str]:
    returncode, stdout, stderr = _git(repo_path, "rev-parse", f"--disambiguate={sha}")
    if returncode != 0:
        return False, "invalid", _git_error(stderr)
    candidates = [line for line in stdout.splitlines() if line.strip()]
    if len(candidates) > 1:
        return False, "ambiguous", f"{len(candidates)} objects share this prefix"
    if candidates:
        return False, "invalid", "not-a-commit"
    return False, "invalid", "missing-object"


def check_ancestor(sha: str, head_sha: str, repo_path: str) -> tuple[bool, str, str]:
    """Classify a SHA as (reachable, status, detail).

    status is reachable, unreachable, ambiguous, or invalid; the gate fails on
    the last three. detail says why an invalid SHA failed: missing-object (not
    in the local clone), not-a-commit, or git-error: <git's first stderr line>.
    """
    # rev-parse --verify --quiet exits 1 when the name does not resolve to a
    # commit; any other nonzero exit is git itself failing.
    returncode, stdout, stderr = _git(
        repo_path, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"
    )
    if returncode == 1:
        return _classify_unresolved(sha, repo_path)
    if returncode != 0:
        return False, "invalid", _git_error(stderr)

    returncode, _, stderr = _git(repo_path, "merge-base", "--is-ancestor", stdout.strip(), head_sha)
    if returncode == 0:
        return True, "reachable", ""
    if returncode == 1:
        return False, "unreachable", ""
    return False, "invalid", _git_error(stderr)
