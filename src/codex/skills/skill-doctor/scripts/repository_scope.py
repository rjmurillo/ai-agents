"""Resolve which checkouts belong to the repository a run grades.

A repository is one Git common directory. Its main checkout and every linked
worktree registered under ``<common>/worktrees`` belong to it. Membership comes
from Git metadata only: the ``.git`` pointer file, the ``commondir`` file, and
each registration's ``gitdir`` file. A directory name, a numbered suffix, or a
shared path prefix never grants membership. The module reads files and never
runs Git, so it cannot change a branch or a working tree.

A rejected root also fences off its own subtree: a session whose deepest
containing root is a rejected one stays out of scope even when a shallower
included root contains it.

Clone discovery (a second clone of the same upstream) is not supported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from session_discovery import (
    copilot_session_matches_repos,
    session_cwd_within_repo,
    session_matches_repos,
)

CLONE_DISCOVERY = "unsupported"
BRANCH_FILTER = "none"
_POINTER_PREFIX = "gitdir:"
_REMOVED = (
    "registered worktree directory is missing (removed); pass --repo PATH to include its sessions"
)
_NOT_POINTING_BACK = "directory exists but its .git does not point back to the registration"
_BAD_REGISTRATION = "registration gitdir file is empty, unreadable, or not a valid path"
_UNREADABLE = "registered worktree directory is unreadable (permission or I/O error)"


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
    _fenced: dict[str, bool] = field(default_factory=dict, repr=False)

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

    def matches(self, harness: str, meta: Any) -> bool:
        """Apply the repository filter, then drop sessions inside a rejected root."""
        if harness == "copilot":
            admitted = copilot_session_matches_repos(meta, self.paths)
            cwds = [meta.get("cwd"), *meta["cwd_history"]]
        else:
            admitted = session_matches_repos(meta.get("cwd"), self.paths)
            cwds = [meta.get("cwd")]
        return admitted and not any(self._fenced_off(cwd) for cwd in cwds)

    def _fenced_off(self, cwd: Any) -> bool:
        key = cwd if isinstance(cwd, str) else ""
        if key not in self._fenced:
            self._fenced[key] = self._deepest_is_rejected(cwd)
        return self._fenced[key]

    def _deepest_is_rejected(self, cwd: Any) -> bool:
        candidates = [(root.path, False) for root in self.rejected]
        candidates += [(root.path, True) for root in self.included]
        containing = [
            (len(path.parts), keeps)
            for path, keeps in candidates
            if session_cwd_within_repo(cwd, path)
        ]
        return bool(containing) and not max(containing)[1]

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


def _resolve(base: Path, text: str) -> Path | None:
    """Resolve a pointer; a malformed one (NUL byte, symlink loop) yields None."""
    try:
        candidate = Path(text)
        return (candidate if candidate.is_absolute() else base / candidate).resolve()
    except (OSError, RuntimeError, ValueError):
        return None


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
    return target if target is not None and target.is_dir() else None


def common_dir_of(git_dir: Path) -> Path:
    text = _read_line(git_dir / "commondir")
    target = _resolve(git_dir, text) if text else None
    return target if target is not None and target.is_dir() else git_dir


def _registrations(common: Path) -> list[tuple[Path, Path | None]]:
    """Return (registration directory, recorded worktree path or None) pairs."""
    root = common / "worktrees"
    try:
        entries = sorted(item for item in root.iterdir() if item.is_dir())
    except OSError:
        return []
    pairs = []
    for entry in entries:
        recorded = _read_line(entry / "gitdir")
        target = _resolve(entry, recorded) if recorded else None
        pairs.append((entry.resolve(), target.parent if target is not None else None))
    return pairs


def _admit_main(scope: RepositoryScope, common: Path) -> None:
    if common.name != ".git":
        scope.reject(
            common, "no main checkout resolved (bare repository or separate git directory)"
        )
    else:
        scope.add(
            ScopeRoot(common.parent, "main", "main checkout of the same Git common directory")
        )


def _admit_worktree(scope: RepositoryScope, registration: Path, worktree: Path | None) -> None:
    if worktree is None:
        scope.reject(registration, _BAD_REGISTRATION)
        return
    try:
        exists = worktree.is_dir()
        points_back = exists and git_dir_of(worktree) == registration
    except OSError:
        scope.reject(worktree, _UNREADABLE)
        return
    if not exists:
        scope.reject(worktree, _REMOVED)
    elif not points_back:
        scope.reject(worktree, _NOT_POINTING_BACK)
    else:
        scope.add(ScopeRoot(worktree, "worktree", "registered linked worktree"))


def _expand(scope: RepositoryScope, selected: Path) -> None:
    git_dir = git_dir_of(selected)
    if git_dir is None:
        scope.add(ScopeRoot(selected, "selected", "explicit path with no Git metadata"))
        return
    common = common_dir_of(git_dir)
    scope.add(ScopeRoot(selected, "selected", "checkout the run started from or was given"))
    _admit_main(scope, common)
    for registration, worktree in _registrations(common):
        _admit_worktree(scope, registration, worktree)


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
