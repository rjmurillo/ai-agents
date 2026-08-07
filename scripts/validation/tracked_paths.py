"""Repository path existence judged from git-tracked content.

Existence checks that read the working tree are not reproducible. A path that
is gitignored build output (for example ``build/audit/``) exists for whoever
just ran the generator and does not exist in CI, so the same commit yields
different results on different machines. Ratchet baselines recorded against a
dirty tree then fail on a clean checkout.

Resolving against the git index removes the machine from the answer.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path, PurePosixPath

_GIT_TIMEOUT_SECONDS = 60


@lru_cache(maxsize=8)
def tracked_paths(repo_root: Path) -> frozenset[str] | None:
    """Return every tracked file and its parent directories, or None.

    None means git could not answer (no repository, git missing, git failed).
    Callers fall back to the filesystem in that case.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            capture_output=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None

    paths: set[str] = set()
    for raw in completed.stdout.decode("utf-8", "replace").split("\0"):
        if not raw:
            continue
        paths.add(raw)
        parents = PurePosixPath(raw).parents
        for parent in parents:
            text = str(parent)
            if text != ".":
                paths.add(text)
    return frozenset(paths)


def path_exists_in_repo(repo_root: Path, rel_path: str) -> bool:
    """Return True when rel_path is tracked, else fall back to the filesystem."""
    known = tracked_paths(repo_root)
    if known is None:
        return (repo_root / rel_path).exists()
    return str(PurePosixPath(rel_path)).strip("/") in known
