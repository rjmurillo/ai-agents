#!/usr/bin/env python3
"""Read ``git worktree list --porcelain`` into ``Worktree`` records.

Porcelain is a stable contract, so parsing it is the one part of this tool that
git guarantees will not change under us. It is separated because it is also the
part with no judgement in it: every safety question is decided elsewhere, from
the records this module produces.

``prunable`` is the line that matters most. Git emits it when it cannot find
the working tree, and it carries a human-readable reason. Dropping the reason
would leave the caller unable to tell a deleted worktree from a moved one.

Related: Issue #2761 (worktree accumulation starves the markdown LSP).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from scripts.maintenance.worktree_report import Worktree


def _apply_attribute(worktree: Worktree, line: str) -> None:
    """Apply one porcelain attribute line to the current worktree record.

    ``HEAD``, ``branch``, ``bare``, ``detached``, ``locked``, and ``prunable``
    are the lines that may follow a ``worktree <path>`` line. Unknown lines are
    ignored.
    """
    if line.startswith("HEAD "):
        worktree.head = line[len("HEAD ") :].strip()
    elif line.startswith("branch "):
        worktree.branch = line[len("branch ") :].strip().removeprefix("refs/heads/")
    elif line == "bare":
        worktree.bare = True
    elif line == "detached":
        worktree.detached = True
    elif line == "locked" or line.startswith("locked "):
        worktree.locked = True
    elif line == "prunable" or line.startswith("prunable "):
        worktree.prunable = line[len("prunable ") :].strip() or "prunable"


def list_worktrees(run_git: Callable[..., str]) -> list[Worktree]:
    """Parse ``git worktree list --porcelain`` into Worktree records.

    The porcelain format groups attributes per worktree, separated by blank
    lines. Each group starts with a ``worktree <path>`` line; attribute lines
    follow and are applied by ``_apply_attribute``.
    """
    raw = run_git(["worktree", "list", "--porcelain"])
    worktrees: list[Worktree] = []
    current: Worktree | None = None

    for line in raw.splitlines():
        if line.startswith("worktree "):
            if current is not None:
                worktrees.append(current)
            current = Worktree(path=line[len("worktree ") :].strip())
        elif current is not None:
            _apply_attribute(current, line)

    if current is not None:
        worktrees.append(current)
    return worktrees
