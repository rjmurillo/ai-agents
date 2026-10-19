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
    run_git,
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
        if backlink and Path(backlink).parent.resolve() == scratch:
            return admin
    return None


def discard_half_created_worktree(
    repo_root: Path, scratch_root: Path, marker_mtime: float
) -> tuple[Path, ...]:
    """Remove a scratch worktree that an interrupted ``git worktree add`` left broken.

    ``git worktree add`` writes the admin directory before it writes
    ``commondir``. A process killed in between leaves an entry that
    ``git worktree remove --force`` refuses ("validation failed"), so the
    ordinary removal can never finish. Only an unlocked entry with no
    ``commondir`` that sits under the harness's scratch roots qualifies. The
    marker-age guard from ``unlock_stale_worktree`` applies, because a younger
    marker may still belong to a live git child. Returns the paths removed,
    which is empty when the worktree is not half created.
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
        removed: list[Path] = []
        if scratch.exists():
            shutil.rmtree(scratch)
            removed.append(scratch)
        pruned = run_git(repo_root, "worktree", "prune")
        if pruned.returncode != 0:
            raise MutationWorkspaceError(f"git worktree prune failed: {pruned.stderr.strip()}")
        if admin.exists():
            raise MutationWorkspaceError(f"git did not prune the worktree entry {admin}")
        removed.append(admin)
    return tuple(removed)
