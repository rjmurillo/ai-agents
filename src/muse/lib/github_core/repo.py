"""Repository root resolution with git worktree awareness."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_DEFAULT_TIMEOUT = 10

#: ``resolve_repo_root`` found the worktree root.
REPO_ROOT_OK = "ok"
#: Git ran and reported that the start directory is not inside a repository.
REPO_ROOT_NOT_A_REPO = "not-a-repo"
#: Git could not answer. The root is unknown, not known to be absent.
REPO_ROOT_GIT_FAILED = "git-failed"

# Git localizes its fatal messages, so the probe below pins LC_ALL=C to make
# this substring deterministic. Any stderr that does not carry it is treated
# as an unexplained failure, which fails closed rather than guessing.
_NOT_A_REPO_STDERR = "not a git repository"


def resolve_repo_root(
    *,
    start_dir: str | Path | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> tuple[Path | None, str]:
    """Return the worktree root together with the reason it is or is not known.

    ``get_repo_root`` collapses two unrelated outcomes into ``None``: there is
    no repository, and git could not be asked. Security callers need to tell
    them apart, because "no repository" is a fact they can act on and "git
    failed" is an absence of information they must not paper over.

    Args:
        start_dir: Directory to run git from (``-C`` flag). ``None`` uses cwd.
        timeout: Subprocess timeout in seconds.

    Returns:
        ``(root, REPO_ROOT_OK)`` when the root is known, otherwise
        ``(None, REPO_ROOT_NOT_A_REPO)`` or ``(None, REPO_ROOT_GIT_FAILED)``.
    """
    cmd: list[str] = ["git"]
    if start_dir is not None:
        cmd.extend(["-C", str(start_dir)])
    cmd.extend(["rev-parse", "--show-toplevel"])

    try:
        result = subprocess.run(  # subprocess-encoding: strict-ok
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, UnicodeDecodeError):
        return None, REPO_ROOT_GIT_FAILED

    if result.returncode != 0:
        stderr = (result.stderr or "").lower()
        if _NOT_A_REPO_STDERR in stderr:
            return None, REPO_ROOT_NOT_A_REPO
        return None, REPO_ROOT_GIT_FAILED

    repo_root = Path(result.stdout.strip())
    if not repo_root.is_absolute():
        # Relative paths are relative to the working directory (or start_dir).
        base = Path(start_dir) if start_dir is not None else Path.cwd()
        repo_root = (base / repo_root).resolve()
    else:
        repo_root = repo_root.resolve()

    return repo_root, REPO_ROOT_OK


def get_repo_root(
    *,
    start_dir: str | Path | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> Path | None:
    """Return the current worktree root, or checkout root outside worktrees.

    Uses ``git rev-parse --show-toplevel`` because callers need the file tree
    root, not the shared Git admin directory. Bare-backed worktrees have a
    common dir outside the checkout, so ``--git-common-dir`` is not a safe
    source for path anchoring.

    Args:
        start_dir: Directory to run git from (``-C`` flag). ``None`` uses cwd.
        timeout: Subprocess timeout in seconds.

    Returns:
        Resolved ``Path`` to the repo root, or ``None`` on failure.

    Note:
        ``None`` conflates "there is no repository" with "git could not be
        asked". Callers that must tell those apart, in particular security
        containment checks, use :func:`resolve_repo_root` instead.
    """
    return resolve_repo_root(start_dir=start_dir, timeout=timeout)[0]
