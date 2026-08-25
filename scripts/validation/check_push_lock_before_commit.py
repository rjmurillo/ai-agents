#!/usr/bin/env python3
"""Refuse a commit while this branch's own push is in flight in this worktree.

Issue #5123: a commit landing in a worktree while that same worktree's
pre-push suite is still running against the same branch can corrupt any test
whose fixture reads live git state (see the root ``conftest.py``
``_guard_real_repo_head`` fixture, issue #3109). The pre-push recipe already
serializes concurrent pushes to one branch behind a per-branch ``flock``; this
guard reuses that SAME lock file rather than inventing a second scheme, per
``.claude/rules/push-lock.md`` MUST NOT 2 ("MUST NOT introduce a second lock
path 'just for this run'"). The lock is held for the whole ``git push``
invocation, which git runs the pre-push hook inside of, so the lock stays
held for the full duration of the pre-push suite, not just the ref transfer.

The canonical lock path is fixed by ``.claude/rules/push-lock.md`` and
``check_push_lock_paths.py``:

    $HOME/src/scratch/locks/push-lock-<slug>.lock

where ``<slug>`` is the current branch name with every ``/`` replaced by
``-``. This checker only ever reads that path's lock state; it never creates
or holds the lock itself beyond the instant it takes to probe it.

EXIT CODES (ADR-035):
  0 - no push is in flight for this branch, or the check does not apply
      (detached HEAD, no lock file has ever been taken for this branch)
  1 - a push for this branch holds the lock right now; the commit is refused
  2 - configuration or runtime error (git command failed)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

LOCK_DIRECTORY = Path.home() / "src" / "scratch" / "locks"

BLOCK_MESSAGE = (
    "push-lock: #5123 a pre-push run for branch {branch!r} appears to be in "
    "flight in this worktree ({lock_path}). Committing now can corrupt any "
    "test whose fixture reads live git state while that run is still reading "
    "it. Wait for the push to finish, then commit. See .claude/rules/push-lock.md."
)


def _current_branch(repo_root: Path) -> str | None:
    """Return the current branch name, or None on a detached HEAD."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "branch", "--show-current"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=10,
    )
    return result.stdout.strip() or None


def lock_path_for_branch(branch: str) -> Path:
    """Return the canonical push-lock path for ``branch`` (push-lock.md)."""
    slug = branch.replace("/", "-")
    return LOCK_DIRECTORY / f"push-lock-{slug}.lock"


if sys.platform == "win32":
    import msvcrt

    def _push_is_in_flight(lock_path: Path) -> bool:
        """Return True when another process holds the exclusive lock."""
        try:
            with lock_path.open("a+b") as handle:
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    return True
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                return False
        except OSError:
            # Cannot open the lock file at all; do not block a commit over an
            # unrelated filesystem problem the push itself would also hit.
            return False
else:
    import fcntl

    def _push_is_in_flight(lock_path: Path) -> bool:
        """Return True when another process holds the exclusive lock."""
        try:
            with lock_path.open("a+b") as handle:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return True
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                return False
        except OSError:
            return False


def check_push_not_in_flight(repo_root: Path) -> tuple[bool, str]:
    """Return ``(allowed, message)``.

    ``allowed`` is False only when a push for the current branch holds the
    canonical lock file right now.
    """
    branch = _current_branch(repo_root)
    if branch is None:
        return True, "push-lock: detached HEAD; the per-branch guard does not apply."
    lock_path = lock_path_for_branch(branch)
    if not lock_path.exists():
        return True, f"push-lock: no lock file yet for branch {branch!r}; allowing commit."
    if _push_is_in_flight(lock_path):
        return False, BLOCK_MESSAGE.format(branch=branch, lock_path=lock_path)
    return True, f"push-lock: branch {branch!r} lock is free; allowing commit."


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    try:
        allowed, message = check_push_not_in_flight(repo_root)
    except (OSError, subprocess.SubprocessError) as error:
        print(f"push-lock: could not evaluate the commit guard: {error}", file=sys.stderr)
        return 2
    print(message)
    return 0 if allowed else 1


if __name__ == "__main__":
    sys.exit(main())
