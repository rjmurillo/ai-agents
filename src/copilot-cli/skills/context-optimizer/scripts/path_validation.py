"""Shared path validation utilities for CWE-22 path traversal prevention.

Provides repo-root-anchored path validation that prevents:
- Symlink traversal (symlinks resolving outside repo)
- Absolute paths (e.g., /etc/passwd)
- Encoded traversal edge cases (e.g., ..%2F)
- Literal .. components that resolve outside repo

See: CWE-22 (https://cwe.mitre.org/data/definitions/22.html)
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def get_repo_root() -> Path:
    """Get the repository root via git rev-parse.

    Returns:
        Resolved Path to the repository root.

    Raises:
        RuntimeError: If not in a git repository or git is unavailable.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        git_common = Path(result.stdout.strip())
        if not git_common.is_absolute():
            git_common = (Path.cwd() / git_common).resolve()
        else:
            git_common = git_common.resolve()
        return git_common.parent
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Unable to determine repository root") from exc


def _get_worktree_root() -> Path | None:
    """Get the current worktree root via git show-toplevel.

    Returns None if not in a worktree or git is unavailable.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return Path(result.stdout.strip()).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def validate_path_within_repo(path: Path, repo_root: Path | None = None) -> Path:
    """Validate that a path resolves within the repository root or worktree.

    Resolves the path and verifies the resolved location is within either
    the main repository root (via git-common-dir) or the current worktree
    root (via show-toplevel). This prevents path traversal via symlinks,
    absolute paths, and .. components that escape the repo boundary while
    remaining worktree-aware.

    Args:
        path: Path to validate (absolute or relative).
        repo_root: Repository root to validate against. If None, determined
            automatically via git rev-parse.

    Returns:
        The resolved path (guaranteed to be within repo or worktree root).

    Raises:
        PermissionError: If the resolved path is outside both roots.
        RuntimeError: If the repository root cannot be determined.
    """
    if repo_root is None:
        repo_root = get_repo_root()

    resolved_root = repo_root.resolve()

    # Anchor relative paths to repo root before resolving.
    # This prevents absolute paths from bypassing containment.
    if not path.is_absolute():
        resolved_path = (resolved_root / path).resolve()
    else:
        resolved_path = path.resolve()

    # Verify containment against main repo root
    if resolved_path.is_relative_to(resolved_root):
        return resolved_path

    # Also accept paths within the current worktree root
    worktree_root = _get_worktree_root()
    if worktree_root and resolved_path.is_relative_to(worktree_root):
        return resolved_path

    raise PermissionError(
        f"Path traversal blocked: '{path}' resolves to '{resolved_path}' "
        f"which is outside repository root '{resolved_root}'"
    )
