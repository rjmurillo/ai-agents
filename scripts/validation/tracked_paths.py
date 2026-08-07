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
_SYMLINK_MODE = "120000"
_MAX_LINK_HOPS = 8


class GitQueryError(RuntimeError):
    """git is present and the path is a repository, but the query failed."""


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
def tracked_paths(repo_root: Path) -> frozenset[str] | None:
    """Return tracked files plus their parent directories, or None.

    None means repo_root is not inside a git repository, or git is not
    installed. Any other failure raises GitQueryError.
    """
    listing = _run_git(repo_root, ["ls-files", "-z"])
    if listing is None:
        return None

    paths: set[str] = set()
    for raw in listing.split("\0"):
        if not raw:
            continue
        paths.add(raw)
        for parent in PurePosixPath(raw).parents:
            text = str(parent)
            if text != ".":
                paths.add(text)
    return frozenset(paths)


@lru_cache(maxsize=8)
def _tracked_symlinks(repo_root: Path) -> dict[str, str]:
    """Return tracked symlink path -> its target text, read from the index.

    The repository tracks a symlink (memory_enhancement -> scripts/...), and
    git lists only the link, so paths beneath it are absent from the index.
    Following it must not consult the working tree: an untracked local link, or
    an unstaged edit to a tracked one, would otherwise decide the answer and
    reintroduce the machine-dependence this module removes.
    """
    listing = _run_git(repo_root, ["ls-files", "-s", "-z"])
    if listing is None:
        return {}

    links: dict[str, str] = {}
    blobs: dict[str, str] = {}
    for entry in listing.split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        fields = meta.split()
        if len(fields) < 2 or fields[0] != _SYMLINK_MODE:
            continue
        blobs[path] = fields[1]

    for path, sha in blobs.items():
        target = _run_git(repo_root, ["cat-file", "blob", sha])
        if target is not None:
            links[path] = target.strip()
    return links


def _resolve_through_index(repo_root: Path, rel_path: str) -> str | None:
    """Rewrite rel_path through tracked symlinks, or None if it does not cross one."""
    links = _tracked_symlinks(repo_root)
    if not links:
        return None

    current = PurePosixPath(rel_path)
    for _ in range(_MAX_LINK_HOPS):
        for depth in range(len(current.parts) - 1, 0, -1):
            prefix = str(PurePosixPath(*current.parts[:depth]))
            target = links.get(prefix)
            if target is None:
                continue
            rest = current.parts[depth:]
            base = PurePosixPath(prefix).parent
            candidate = PurePosixPath(base / target, *rest)
            if ".." in candidate.parts or candidate.is_absolute():
                return None
            current = candidate
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

    known = tracked_paths(repo_root)
    if known is None:
        return (repo_root / normalized).exists()
    if normalized in known:
        return True

    through_link = _resolve_through_index(repo_root, normalized)
    return through_link is not None and through_link in known
