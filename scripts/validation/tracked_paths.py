"""Repository path existence judged from git-tracked content.

Existence checks that read the working tree are not reproducible. A path that
is gitignored build output (for example ``build/audit/``) exists for whoever
just ran the generator and does not exist in CI, so the same commit yields
different results on different machines. Ratchet baselines recorded against a
dirty tree then fail on a clean checkout.

Resolving against the git index removes the machine from the answer.

Semantics, stated because they are load-bearing for callers:

* The answer comes from the git **index** (``git ls-files``), not from HEAD, so
  a staged addition counts as existing and a staged deletion does not. That is
  deliberate: a validator should see the tree the commit will have.
* The index is read once per repository root and cached for the life of the
  process. Callers that mutate the index mid-process must call
  ``tracked_paths.cache_clear()``.
* Only a genuine "not a git repository", or a missing git binary, falls back to
  the filesystem, which is what lets callers validate scratch directories.
  Operational git failures raise, because silently falling back would restore
  the exact machine-dependence this module exists to remove.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path, PurePosixPath

_GIT_TIMEOUT_SECONDS = 60
_NOT_A_REPOSITORY = "not a git repository"


class GitQueryError(RuntimeError):
    """git is present and the path is a repository, but the query failed."""


@lru_cache(maxsize=8)
def tracked_paths(repo_root: Path) -> frozenset[str] | None:
    """Return tracked files plus their parent directories, or None.

    None means repo_root is not inside a git repository, or git is not
    installed. Any other failure raises GitQueryError rather than degrading to
    a filesystem answer.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            capture_output=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return None
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitQueryError(f"git ls-files failed for {repo_root}: {exc}") from exc

    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", "replace")
        if _NOT_A_REPOSITORY in stderr.lower():
            return None
        raise GitQueryError(
            f"git ls-files failed for {repo_root} "
            f"(exit {completed.returncode}): {stderr.strip()}"
        )

    paths: set[str] = set()
    for raw in completed.stdout.decode("utf-8", "replace").split("\0"):
        if not raw:
            continue
        paths.add(raw)
        for parent in PurePosixPath(raw).parents:
            text = str(parent)
            if text != ".":
                paths.add(text)
    return frozenset(paths)


def _normalize(rel_path: str) -> str | None:
    """Return a repo-relative posix path, or None if the input is not one."""
    posix = PurePosixPath(rel_path)
    if posix.is_absolute() or ".." in posix.parts:
        return None
    return str(posix).strip("/")


def _resolves_to_tracked(
    repo_root: Path, rel_path: str, known: frozenset[str]
) -> bool:
    """Return True when rel_path reaches a tracked path through a tracked symlink.

    The repository tracks a symlink (memory_enhancement -> scripts/...), and git
    lists only the link itself, so paths beneath it are absent from the index.
    Following it stays reproducible: both the link and its target are tracked,
    so every clone agrees.
    """
    root = repo_root.resolve()
    try:
        target = (repo_root / rel_path).resolve()
        relative = target.relative_to(root)
    except (OSError, ValueError):
        return False
    return str(PurePosixPath(relative)) in known


def path_exists_in_repo(repo_root: Path, rel_path: str) -> bool:
    """Return True when rel_path is tracked; fall back only outside a repository."""
    normalized = _normalize(rel_path)
    if normalized is None:
        return False

    known = tracked_paths(repo_root)
    if known is None:
        return (repo_root / normalized).exists()
    if normalized in known:
        return True
    return _resolves_to_tracked(repo_root, normalized, known)
