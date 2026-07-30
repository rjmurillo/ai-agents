"""Locate a scratch root that sits outside every enclosing git repository."""

from __future__ import annotations

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
