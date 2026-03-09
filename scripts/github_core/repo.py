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
    """Return the main repository root, even when called from a worktree.

    Uses ``git rev-parse --git-common-dir`` which resolves to the main
    repo's ``.git`` directory regardless of whether the current working
    directory is a worktree or the main checkout.

    Args:
        start_dir: Directory to run git from (``-C`` flag). ``None`` uses cwd.
        timeout: Subprocess timeout in seconds.

    Returns:
        Resolved ``Path`` to the repo root, or ``None`` on failure.
    """
    cmd: list[str] = ["git"]
    if start_dir is not None:
        cmd.extend(["-C", str(start_dir)])
    cmd.extend(["rev-parse", "--git-common-dir"])

    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    if result.returncode != 0:
        return None

    git_common = Path(result.stdout.strip())
    if not git_common.is_absolute():
        # Relative paths are relative to the working directory (or start_dir)
        base = Path(start_dir) if start_dir is not None else Path.cwd()
        git_common = (base / git_common).resolve()
    else:
        git_common = git_common.resolve()

    return git_common.parent
