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
  ``clear_tracked_path_cache()``.
* Only a genuine "not a git repository", or a missing git binary, falls back to
  the filesystem, which is what lets callers validate scratch directories.
  Operational git failures raise, because silently falling back would restore
  the exact machine-dependence this module exists to remove.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath

_GIT_TIMEOUT_SECONDS = 60
_NOT_A_REPOSITORY = "not a git repository"
_SYMLINK_MODE = "120000"
_MAX_LINK_HOPS = 8


class GitQueryError(RuntimeError):
    """git is present and the path is a repository, but the query failed."""


@dataclass(frozen=True)
class _IndexSnapshot:
    paths: frozenset[str]
    symlinks: dict[str, str]


def _run_git(repo_root: Path, args: list[str]) -> str | None:
    """Run a git command under repo_root. None means "not a repository".

    Any other failure raises GitQueryError. Degrading to a filesystem answer on
    an operational failure would restore the machine-dependence this module
    exists to remove.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return None
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitQueryError(f"git {args[0]} failed for {repo_root}: {exc}") from exc

    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", "replace")
        if _NOT_A_REPOSITORY in stderr.lower():
            return None
        raise GitQueryError(
            f"git {args[0]} failed for {repo_root} "
            f"(exit {completed.returncode}): {stderr.strip()}"
        )
    return completed.stdout.decode("utf-8", "replace")


@lru_cache(maxsize=8)
def _index_snapshot(repo_root: Path) -> _IndexSnapshot | None:
    """Return one coherent snapshot of tracked paths and symlinks."""
    listing = _run_git(repo_root, ["ls-files", "-s", "-z"])
    if listing is None:
        return None

    paths: set[str] = set()
    blobs: dict[str, str] = {}
    for entry in listing.split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        fields = meta.split()
        if len(fields) < 2:
            continue
        paths.add(path)
        for parent in PurePosixPath(path).parents:
            text = str(parent)
            if text != ".":
                paths.add(text)
        if fields[0] == _SYMLINK_MODE:
            blobs[path] = fields[1]

    links: dict[str, str] = {}
    for path, sha in blobs.items():
        target = _run_git(repo_root, ["cat-file", "blob", sha])
        if target is not None:
            links[path] = target.strip()
    return _IndexSnapshot(frozenset(paths), links)


def clear_tracked_path_cache() -> None:
    """Discard the cached index snapshot after a caller mutates the index."""
    _index_snapshot.cache_clear()


def tracked_paths(repo_root: Path) -> frozenset[str] | None:
    """Return tracked files plus their parent directories, or None."""
    snapshot = _index_snapshot(repo_root)
    return None if snapshot is None else snapshot.paths


def _collapse_repo_path(path: PurePosixPath) -> str | None:
    """Collapse dot segments, rejecting only paths that escape the repo."""
    parts: list[str] = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _resolve_through_index(repo_root: Path, rel_path: str) -> str | None:
    """Rewrite rel_path through tracked symlinks, or None if it does not cross one."""
    snapshot = _index_snapshot(repo_root)
    if snapshot is None or not snapshot.symlinks:
        return None

    current = PurePosixPath(rel_path)
    for _ in range(_MAX_LINK_HOPS):
        for depth in range(len(current.parts) - 1, 0, -1):
            prefix = str(PurePosixPath(*current.parts[:depth]))
            target = snapshot.symlinks.get(prefix)
            if target is None:
                continue
            target_path = PurePosixPath(target)
            if target_path.is_absolute():
                return None
            rest = current.parts[depth:]
            base = PurePosixPath(prefix).parent
            collapsed = _collapse_repo_path(PurePosixPath(base / target_path, *rest))
            if collapsed is None:
                return None
            current = PurePosixPath(collapsed)
            break
        else:
            return str(current) if str(current) != rel_path else None
    return None


def _normalize(rel_path: str) -> str | None:
    """Return a repo-relative posix path, or None if the input is not one."""
    posix = PurePosixPath(rel_path)
    if posix.is_absolute() or ".." in posix.parts:
        return None
    return str(posix).strip("/")


def path_exists_in_repo(repo_root: Path, rel_path: str) -> bool:
    """Return True when rel_path is tracked; fall back only outside a repository."""
    normalized = _normalize(rel_path)
    if normalized is None:
        return False

    snapshot = _index_snapshot(repo_root)
    if snapshot is None:
        return (repo_root / normalized).exists()
    if normalized in snapshot.paths:
        return True

    through_link = _resolve_through_index(repo_root, normalized)
    return through_link is not None and through_link in snapshot.paths
