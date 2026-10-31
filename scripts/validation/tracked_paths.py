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


def _run_git_bytes(repo_root: Path, args: list[str], stdin: bytes | None = None) -> bytes | None:
    """Run a git command under repo_root and return raw stdout.

    None means "not a repository". Any other failure raises GitQueryError.
    Degrading to a filesystem answer on an operational failure would restore
    the machine-dependence this module exists to remove. ``stdin`` feeds a
    command that reads its object list from standard input.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            input=stdin,
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
            f"git {args[0]} failed for {repo_root} (exit {completed.returncode}): {stderr.strip()}"
        )
    return completed.stdout


def _run_git(repo_root: Path, args: list[str]) -> str | None:
    """Run a git command under repo_root and return decoded stdout.

    None means "not a repository"; see :func:`_run_git_bytes` for the rest.
    """
    raw = _run_git_bytes(repo_root, args)
    return None if raw is None else raw.decode("utf-8", "replace")


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

    return _IndexSnapshot(frozenset(paths), _read_link_targets(repo_root, blobs))


def _read_link_targets(repo_root: Path, blobs: dict[str, str]) -> dict[str, str]:
    """Read every tracked symlink's target with one ``git cat-file --batch``.

    The index lists a few hundred symlinks (ADR-119 links the dogfood trees to
    the shipped plugin trees), and a ``git cat-file blob`` process per link cost
    about a second of fork and exec time on every gate that checks path
    existence (issue #6734). One batch process answers all of them.

    Each object is requested as ``<sha>^{blob}``, which peels an annotated tag
    to its blob the way ``git cat-file blob <sha>`` did; a bare sha would return
    the tag object itself. Each reply is a ``<oid> blob <size>`` header line,
    then the blob bytes, then one line feed, in request order. A reply that is
    ``missing`` (absent object, or one that does not peel to a blob), a header
    of any other shape, or a stream that ends early raises, matching the
    per-blob call, which exited non-zero in those cases. A blob body without
    its closing line feed also raises, so a cut-off reply is never read as a
    target. A repository the first
    ``ls-files`` call could read but this one reports as not a repository yields
    no links, as the per-blob call did.
    """
    if not blobs:
        return {}
    shas = list(dict.fromkeys(blobs.values()))
    request = "".join(f"{sha}^{{blob}}\n" for sha in shas).encode("ascii")
    completed = _run_git_bytes(repo_root, ["cat-file", "--batch"], request)
    if completed is None:
        return {}
    targets: dict[str, str] = {}
    offset = 0
    for sha in shas:
        newline = completed.find(b"\n", offset)
        header = (
            completed[offset:newline].decode("utf-8", "replace").split() if newline >= 0 else []
        )
        if len(header) != 3 or header[1] != "blob" or not header[2].isdigit():
            raise GitQueryError(
                f"git cat-file --batch failed for {repo_root}: unexpected reply for {sha}: "
                f"{' '.join(header) or 'truncated output'}"
            )
        start = newline + 1
        end = start + int(header[2])
        if end >= len(completed) or completed[end] != 0x0A:
            raise GitQueryError(
                f"git cat-file --batch failed for {repo_root}: truncated blob for {sha}"
            )
        targets[sha] = completed[start:end].decode("utf-8", "replace").strip()
        offset = end + 1
    return {path: targets[sha] for path, sha in blobs.items()}


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
