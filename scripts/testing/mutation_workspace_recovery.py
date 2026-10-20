"""Recovery of scratch worktrees that an interrupted ``git worktree add`` left broken."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from scripts.testing.mutation_workspace_git import (
    GIT_COMMAND_TIMEOUT_SECONDS,
    MutationWorkspaceError,
    _require_scratch_path,
    _serialized_worktree_state,
    require_git_stdout,
)


def _admin_dir_unlocked(repo_root: Path, scratch: Path) -> Path | None:
    """Return the git admin directory whose ``gitdir`` backlink names ``scratch``.

    The backlink is read from ``<common dir>/worktrees/*/gitdir`` instead of the
    scratch ``.git`` pointer, because an interrupted ``git worktree add`` can
    leave the pointer file absent while the admin directory exists.
    """
    common = require_git_stdout(
        repo_root, "rev-parse", "--git-common-dir", error="cannot locate git common directory"
    )
    common_dir = Path(common)
    if not common_dir.is_absolute():
        common_dir = repo_root / common_dir
    worktrees_dir = common_dir.resolve() / "worktrees"
    if not worktrees_dir.is_dir():
        return None
    for admin in sorted(worktrees_dir.iterdir()):
        try:
            backlink = (admin / "gitdir").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not backlink:
            continue
        link = Path(backlink)
        if not link.is_absolute():
            # worktree.useRelativePaths stores the link relative to the admin dir.
            link = admin / link
        if link.parent.resolve() == scratch:
            return admin
    return None


def _scratch_is_owned_by(scratch: Path, admin: Path) -> bool:
    """Return True when ``scratch`` is empty or its ``.git`` pointer names ``admin``.

    The admin backlink records a pathname, not the identity of what sits there
    now. A directory created later under the same path must survive recovery.
    """
    pointer = scratch / ".git"
    if pointer.is_file():
        try:
            text = pointer.read_text(encoding="utf-8").strip()
        except OSError:
            return False
        if not text.startswith("gitdir:"):
            return False
        target = Path(text.removeprefix("gitdir:").strip())
        if not target.is_absolute():
            target = scratch / target
        return target.resolve() == admin.resolve()
    if pointer.exists() or not scratch.is_dir():
        return False
    return not any(scratch.iterdir())


def discard_half_created_worktree(
    repo_root: Path, scratch_root: Path, marker_mtime: float
) -> tuple[Path, ...]:
    """Remove a scratch worktree that an interrupted ``git worktree add`` left broken.

    ``git worktree add`` writes the admin directory before it writes
    ``commondir``. A process killed in between leaves an entry that
    ``git worktree remove --force`` refuses ("validation failed"), so the
    ordinary removal can never finish. Only an unlocked entry with no
    ``commondir`` that sits under the harness's scratch roots qualifies. Only
    that one admin directory is removed, never the whole registry. The scratch
    directory is deleted only when its ``.git`` pointer names the admin entry
    or the directory is empty. The marker-age guard from ``unlock_stale_worktree``
    applies, because a younger marker may still belong to a live git child.
    Returns the paths removed, which is empty when the worktree is not half
    created.
    """
    scratch = _require_scratch_path(repo_root, scratch_root, "discard")
    with _serialized_worktree_state(repo_root):
        admin = _admin_dir_unlocked(repo_root, scratch)
        if admin is None or (admin / "commondir").exists() or (admin / "locked").exists():
            return ()
        age = time.time() - marker_mtime
        if age < GIT_COMMAND_TIMEOUT_SECONDS:
            raise MutationWorkspaceError(
                f"worktree {scratch} is half created; its marker is {age:.0f}s old, "
                f"retry after {GIT_COMMAND_TIMEOUT_SECONDS}s"
            )
        if scratch.is_symlink() or (scratch.exists() and not _scratch_is_owned_by(scratch, admin)):
            raise MutationWorkspaceError(
                f"worktree {scratch} is half created, but the directory is not the "
                f"interrupted checkout; move it aside and rerun recover"
            )
        removed: list[Path] = []
        if scratch.exists():
            shutil.rmtree(scratch)
            removed.append(scratch)
        shutil.rmtree(admin)
        removed.append(admin)
    return tuple(removed)
