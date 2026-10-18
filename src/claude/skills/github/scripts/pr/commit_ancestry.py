"""Classify a commit SHA against a pull request head in a local clone.

Split out of check_review_thread_resolution_shas.py to keep that script under
the 500-line taste limit. Stdlib only, so it runs under bare python3.
"""

from __future__ import annotations

import re
import subprocess

_GIT_TIMEOUT_SECONDS = 30
_HEX_SHA = re.compile(r"[0-9a-fA-F]{4,40}")


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


def _shadowing_ref(sha: str, repo_path: str) -> tuple[bool, str]:
    """Return (shadowed, git stderr): whether a ref is named exactly like ``sha``.

    ``git rev-parse`` tries a ref of that name before an object-name prefix, so
    a branch or tag called ``abc1234`` makes a cited ``abc1234`` resolve to the
    ref's tip instead of the commit the reviewer meant. The names tried are the
    ``gitrevisions`` dwim list after ``$GIT_DIR/<name>``, which a lowercase
    ``sha`` cannot match (``check_ancestor`` lowercases). ``sha`` is hex only,
    so the patterns carry no glob characters; ``for-each-ref`` also lists refs
    below a match, so the output is compared to the exact names.
    """
    exact = {
        f"refs/{sha}",
        f"refs/tags/{sha}",
        f"refs/heads/{sha}",
        f"refs/remotes/{sha}",
        f"refs/remotes/{sha}/HEAD",
    }
    returncode, stdout, stderr = _git(
        repo_path,
        "for-each-ref",
        "--format=%(refname)",
        f"refs/{sha}",
        f"refs/tags/{sha}",
        f"refs/heads/{sha}",
        f"refs/remotes/{sha}",
    )
    if returncode != 0:
        return False, stderr or f"git for-each-ref exited {returncode}"
    return any(line.strip() in exact for line in stdout.splitlines()), ""


def check_ancestor(sha: str, head_sha: str, repo_path: str) -> tuple[bool, str, str]:
    """Classify a SHA as (reachable, status, detail).

    status is reachable, unreachable, ambiguous, or invalid; the gate fails on
    the last three. detail says why an invalid SHA failed: not-a-sha (not 4 to
    40 hex digits), ref-name-collision (a ref carries the same name, so git
    would resolve the ref, not the commit), missing-object (not in the local
    clone), not-a-commit, or git-error: <git's first stderr line>.

    The SHA is lowercased before git sees it. Object-name prefixes are case
    insensitive, but git reads an all-uppercase name as a root ref under
    ``$GIT_DIR`` (``$GIT_DIR/ABC1234``) before it tries an object. A lowercase
    name is never a root ref, so the first dwim entry cannot shadow it.
    """
    if not _HEX_SHA.fullmatch(sha):
        return False, "invalid", "not-a-sha"
    sha = sha.lower()
    # rev-parse --verify --quiet exits 1 when the name does not resolve to a
    # commit; any other nonzero exit is git itself failing.
    returncode, stdout, stderr = _git(
        repo_path, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"
    )
    if returncode == 1:
        return _classify_unresolved(sha, repo_path)
    if returncode != 0:
        return False, "invalid", _git_error(stderr)

    shadowed, probe_error = _shadowing_ref(sha, repo_path)
    if probe_error:
        return False, "invalid", _git_error(probe_error)
    if shadowed:
        return False, "invalid", "ref-name-collision"

    returncode, _, stderr = _git(repo_path, "merge-base", "--is-ancestor", stdout.strip(), head_sha)
    if returncode == 0:
        return True, "reachable", ""
    if returncode == 1:
        return False, "unreachable", ""
    return False, "invalid", _git_error(stderr)
