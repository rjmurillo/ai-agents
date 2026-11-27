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

Linked worktrees are often short lived. A session whose working directory no
longer exists stays in scope when it recorded a branch this repository still
has, other than the default branch, and no other checkout now owns that path.
Claude Code records ``gitBranch`` and Codex records ``git.branch``. The other
harnesses record no branch, so their sessions in a removed worktree stay out.

Clone discovery (a second clone of the same upstream) is not supported.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
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
    "registered worktree directory is missing (removed); its sessions stay in scope when they "
    "recorded a branch this repository still has, pass --repo PATH to include the others"
)
_DEFAULT_BRANCHES = frozenset({"main", "master"})
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
    commons: set[Path] = field(default_factory=set)
    branches: set[str] = field(default_factory=set)
    branch_admitted: int = 0

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
        """Apply the repository filter, then drop sessions inside a rejected root.

        A session in a removed checkout is admitted by its recorded branch instead.
        """
        if harness == "copilot":
            admitted = copilot_session_matches_repos(meta, self.paths)
            cwds = [meta.get("cwd"), *meta["cwd_history"]]
        else:
            admitted = session_matches_repos(meta.get("cwd"), self.paths)
            cwds = [meta.get("cwd")]
        if admitted and not any(self._fenced_off(cwd) for cwd in cwds):
            return True
        if harness != "copilot" and self._removed_checkout_on_branch(meta):
            self.branch_admitted += 1
            return True
        return False

    def _removed_checkout_on_branch(self, meta: Any) -> bool:
        """True for a vanished cwd whose session recorded a non-default branch of this repo."""
        branch = session_branch(meta)
        if branch is None or branch not in self.branches:
            return False
        cwd = meta.get("cwd")
        if not isinstance(cwd, str) or bool(PureWindowsPath(cwd).drive) != (os.name == "nt"):
            return False
        path = Path(cwd)
        try:
            if not path.is_absolute() or path.exists():
                return False
            owner = _enclosing_common_dir(path)
        except OSError:
            return False
        return owner is None or owner in self.commons

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
            "removed_checkout_sessions": self.branch_admitted,
        }


def session_branch(meta: Any) -> str | None:
    """The branch a session recorded: Claude Code ``git_branch`` or Codex ``git.branch``."""
    branch = meta.get("git_branch")
    git = meta.get("git")
    if branch is None and isinstance(git, dict):
        branch = git.get("branch")
    return branch if isinstance(branch, str) and branch else None


def _enclosing_common_dir(path: Path) -> Path | None:
    """Common directory of the checkout holding the nearest existing ancestor, if any."""
    ancestors = [parent for parent in path.parents if parent.exists()]
    for ancestor in ancestors:
        if (ancestor / ".git").exists():
            git_dir = git_dir_of(ancestor)
            return common_dir_of(git_dir) if git_dir is not None else ancestor
    return None


def _ref_names(common: Path) -> set[str]:
    """Local and remote-tracking branch names, from loose refs and ``packed-refs``."""
    names: set[str] = set()
    for prefix, depth in (("refs/heads/", 0), ("refs/remotes/", 1)):
        root = common / prefix
        try:
            files = [item for item in root.rglob("*") if item.is_file()]
        except OSError:
            files = []
        for item in files:
            parts = item.relative_to(root).parts[depth:]
            if parts and parts != ("HEAD",):
                names.add("/".join(parts))
    for line in (_read_text(common / "packed-refs") or "").splitlines():
        ref = line.partition(" ")[2]
        for prefix, depth in (("refs/heads/", 0), ("refs/remotes/", 1)):
            if ref.startswith(prefix):
                parts = tuple(ref[len(prefix) :].split("/"))[depth:]
                if parts and parts != ("HEAD",):
                    names.add("/".join(parts))
    return names


def branch_names(common: Path) -> set[str]:
    """Non-default branch names a removed checkout of this repository could have used."""
    defaults = set(_DEFAULT_BRANCHES)
    try:
        heads = sorted((common / "refs" / "remotes").glob("*/HEAD"))
    except OSError:
        heads = []
    for head in heads:
        target = _read_line(head) or ""
        if target.startswith("ref: refs/remotes/"):
            defaults.add(target.split("/", 3)[-1])
    return _ref_names(common) - defaults


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _read_line(path: Path) -> str | None:
    text = _read_text(path)
    return text.strip() if text is not None else None


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


def _expand(scope: RepositoryScope, selected: Path, expanded: set[Path]) -> None:
    """Add ``selected``; expand its common directory once per ``expanded`` set."""
    git_dir = git_dir_of(selected)
    if git_dir is None:
        scope.add(ScopeRoot(selected, "selected", "explicit path with no Git metadata"))
        return
    common = common_dir_of(git_dir)
    scope.add(ScopeRoot(selected, "selected", "checkout the run started from or was given"))
    if common in expanded:
        return
    expanded.add(common)
    scope.commons.add(common)
    scope.branches |= branch_names(common)
    _admit_main(scope, common)
    for registration, worktree in _registrations(common):
        _admit_worktree(scope, registration, worktree)


def resolve_repository_scope(repos: Any, expand: bool = True) -> RepositoryScope:
    """Expand each selected checkout to its repository's registered checkouts.

    With ``expand`` false, every selected path stands alone.
    """
    scope = RepositoryScope()
    expanded: set[Path] = set()
    for repo in repos:
        if expand:
            _expand(scope, Path(repo), expanded)
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
