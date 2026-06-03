"""Repository root resolution with git worktree awareness."""

from __future__ import annotations

import subprocess
from pathlib import Path

_DEFAULT_TIMEOUT = 10


def get_repo_root(
    *,
    start_dir: str | Path | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> Path | None:
    """Return the current worktree root.

    Uses ``git rev-parse --show-toplevel`` so isolated git worktrees resolve to
    their own checkout root instead of the bare repository's parent directory.

    Args:
        start_dir: Directory to run git from (``-C`` flag). ``None`` uses cwd.
        timeout: Subprocess timeout in seconds.

    Returns:
        Resolved ``Path`` to the repo root, or ``None`` on failure.
    """
    cmd: list[str] = ["git"]
    if start_dir is not None:
        cmd.extend(["-C", str(start_dir)])
    cmd.extend(["rev-parse", "--show-toplevel"])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    if result.returncode != 0:
        return None

    repo_root = Path(result.stdout.strip())
    if not repo_root.is_absolute():
        base = Path(start_dir) if start_dir is not None else Path.cwd()
        repo_root = (base / repo_root).resolve()
    else:
        repo_root = repo_root.resolve()

    return repo_root
