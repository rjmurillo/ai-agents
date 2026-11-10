"""Resolve which checkouts belong to the repository a run grades.

A repository is one Git common directory. Its main checkout and every linked
worktree registered under ``<common>/worktrees`` belong to it. Membership comes
from Git metadata only: the ``.git`` pointer file, the ``commondir`` file, and
each registration's ``gitdir`` file. A directory name, a numbered suffix, or a
shared path prefix never grants membership. The module reads files and never
runs Git, so it cannot change a branch or a working tree.

Clone discovery (a second clone of the same upstream) is not supported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from session_discovery import session_cwd_within_repo

CLONE_DISCOVERY = "unsupported"
BRANCH_FILTER = "none"
_POINTER_PREFIX = "gitdir:"


@dataclass(frozen=True)
class ScopeRoot:
    path: Path
    kind: str
    reason: str


@dataclass(frozen=True)
class RejectedRoot:
    path: Path
    reason: str


@dataclass
class RepositoryScope:
    included: list[ScopeRoot] = field(default_factory=list)
    rejected: list[RejectedRoot] = field(default_factory=list)

    @property
    def paths(self) -> list[Path]:
        return [root.path for root in self.included]

    def add(self, root: ScopeRoot) -> None:
        if root.path not in self.paths:
            self.included.append(root)
            self.rejected = [item for item in self.rejected if item.path != root.path]

    def reject(self, path: Path, reason: str) -> None:
        if path not in self.paths and all(item.path != path for item in self.rejected):
            self.rejected.append(RejectedRoot(path, reason))

    def report(self, sessions: Any = ()) -> dict[str, Any]:
        counts = count_sessions_by_root(sessions, self.paths)
        return {
            "clone_discovery": CLONE_DISCOVERY,
            "branch_filter": BRANCH_FILTER,
            "included": [
                {
                    "path": str(root.path),
                    "kind": root.kind,
                    "reason": root.reason,
                    "sessions_considered": counts[root.path],
                }
                for root in self.included
            ],
            "rejected": [{"path": str(item.path), "reason": item.reason} for item in self.rejected],
        }


def _read_line(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _resolve(base: Path, text: str) -> Path:
    candidate = Path(text)
    return (candidate if candidate.is_absolute() else base / candidate).resolve()


def git_dir_of(checkout: Path) -> Path | None:
    """Return the Git directory a checkout's ``.git`` entry points at."""
    entry = checkout / ".git"
    if entry.is_dir():
        return entry.resolve()
    if not entry.is_file():
        return None
    text = _read_line(entry)
    if not text or not text.startswith(_POINTER_PREFIX):
        return None
    target = _resolve(checkout, text[len(_POINTER_PREFIX) :].strip())
    return target if target.is_dir() else None


def common_dir_of(git_dir: Path) -> Path:
    text = _read_line(git_dir / "commondir")
    if not text:
        return git_dir
    target = _resolve(git_dir, text)
    return target if target.is_dir() else git_dir


def _registrations(common: Path) -> list[tuple[Path, Path]]:
    """Return (registration directory, recorded worktree path) pairs."""
    root = common / "worktrees"
    try:
        entries = sorted(item for item in root.iterdir() if item.is_dir())
    except OSError:
        return []
    pairs = []
    for entry in entries:
        recorded = _read_line(entry / "gitdir")
        if recorded:
            pairs.append((entry.resolve(), _resolve(entry, recorded).parent))
    return pairs


def _main_checkout(common: Path) -> Path | None:
    if common.name != ".git":
        return None
    parent = common.parent
    return parent if git_dir_of(parent) == common else None


def _expand(scope: RepositoryScope, selected: Path) -> None:
    git_dir = git_dir_of(selected)
    if git_dir is None:
        scope.add(ScopeRoot(selected, "selected", "explicit path with no Git metadata"))
        return
    common = common_dir_of(git_dir)
    scope.add(ScopeRoot(selected, "selected", "checkout the run started from or was given"))
    main = _main_checkout(common)
    if main is not None:
        scope.add(ScopeRoot(main, "main", "main checkout of the same Git common directory"))
    for registration, worktree in _registrations(common):
        _admit_worktree(scope, registration, worktree)


def _admit_worktree(scope: RepositoryScope, registration: Path, worktree: Path) -> None:
    if not worktree.is_dir():
        scope.reject(
            worktree,
            "registered worktree directory is missing (removed); "
            "pass --repo PATH to include its sessions",
        )
    elif git_dir_of(worktree) != registration:
        scope.reject(
            worktree, "directory exists but its .git does not point back to the registration"
        )
    else:
        scope.add(ScopeRoot(worktree, "worktree", "registered linked worktree"))


def resolve_repository_scope(repos: Any, expand: bool = True) -> RepositoryScope:
    """Expand each selected checkout to its repository's registered checkouts.

    With ``expand`` false, every selected path stands alone.
    """
    scope = RepositoryScope()
    for repo in repos:
        if expand:
            _expand(scope, Path(repo))
        else:
            scope.add(ScopeRoot(Path(repo), "selected", "listed path only (--no-worktrees)"))
    return scope


def count_sessions_by_root(sessions: Any, roots: Any) -> dict[Path, int]:
    """Attribute each session to the deepest root containing its working directory."""
    counts = dict.fromkeys(roots, 0)
    ordered = sorted(roots, key=lambda root: len(root.parts), reverse=True)
    for session in sessions:
        cwd = session["meta"].get("cwd")
        for root in ordered:
            if session_cwd_within_repo(cwd, root):
                counts[root] += 1
                break
    return counts


def print_scope_roots(resolution: Any, limit: int = 20) -> None:
    included, rejected = resolution["included"], resolution["rejected"]
    if included or rejected:
        print(
            f"scope roots:       {len(included)} included (selected checkout, main checkout, "
            f"registered worktrees), {len(rejected)} rejected"
        )
    for root in included[:limit]:
        print(
            f"  included {root['kind']:<9} {root['path']} ({root['sessions_considered']} scoreable)"
        )
    for root in rejected[:limit]:
        print(f"  rejected {root['path']}: {root['reason']}")
    hidden = max(len(included) - limit, 0) + max(len(rejected) - limit, 0)
    if hidden:
        print(f"  ... {hidden} more roots listed in inventory.json")
    print(
        f"clone discovery: {resolution['clone_discovery']}; "
        f"conversation branch filter: {resolution['branch_filter']}"
    )
