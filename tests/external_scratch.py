"""Locate a scratch root that sits outside every enclosing git repository."""

from __future__ import annotations

import shutil
from pathlib import Path


def outside_every_repository(start: Path) -> Path:
    """Return the nearest ancestor of *start* with no ``.git`` at or above it.

    Path-boundary tests need a directory whose ancestors hold no repository, so
    that a walk upward terminates the way it does outside a checkout. Deriving
    that from the immediate parent of the project root is wrong whenever the
    checkout is a git worktree nested under the main repository, the layout
    agent work uses: the parent is then still inside the main repository, the
    walk finds it, and a test asserting "no repository above here" fails on a
    correct implementation.

    The outermost ancestor holding a ``.git`` is the last repository on the
    chain, so its parent has no repository at or above it by construction.
    ``.git`` is a directory in a normal checkout and a file in a worktree, so
    existence is the test rather than directory-ness.
    """
    outermost: Path | None = None
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            outermost = candidate
    return start if outermost is None else outermost.parent


def make_external_dir(root: Path, name: str) -> Path:
    """Create ``root/name``, retrying when a sibling worker removes ``root``.

    ``remove_external_dir`` drops ``root`` once it is empty, so under xdist a
    sibling can delete it between creating ``root`` and creating the child.
    A second attempt recreates it.
    """
    path = root / name
    for attempt in range(3):
        try:
            path.mkdir(parents=True)
            return path
        except FileNotFoundError:
            if attempt == 2:
                raise
    return path


def remove_external_dir(path: Path) -> None:
    """Delete *path*, then its parent root when no other worker still uses it.

    Without the second step every checkout that runs the suite leaves an empty
    ``.pytest-external-<checkout>`` directory beside it.
    """
    shutil.rmtree(path, ignore_errors=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass
