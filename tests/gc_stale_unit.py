"""Shared setup for the stale-entry unit suites.

Two suites ask different questions about the same fabricated worktree: what
``decide`` reports about a stale entry, and what warnings the reason carries.
They need the same stubs, so the stubs live here rather than in either file.

This is a plain module, not a ``conftest.py``. The pre-removal HEAD stub has to
be autouse, and a ``conftest.py`` under ``tests/`` would apply it to every suite
in the directory, including the real-git ones that need the real read. Each
suite wraps :func:`stub_pre_removal_head` in its own autouse fixture instead, so
the blast radius is one file.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from scripts.maintenance.gc_worktrees import Decision, Worktree, decide

MAIN = "/repo/main"
BASE = "origin/main"
SHA = "f30c6952bf2da328bcff0aecc74ff05de3558df7"
MODULE = "scripts.maintenance.gc_worktrees"
STUB_HEAD = "f" * 40


@contextmanager
def stub_pre_removal_head() -> Iterator[None]:
    """Hold the pre-removal HEAD read to a fixed value.

    ``apply_removals`` reads each candidate's HEAD twice, once with the recheck
    and once immediately before removing it, and refuses when the two differ.
    Against a fabricated path both reads fail and every removal is withheld,
    which would hide what these tests are actually about. Tests that care about
    the comparison patch it again with their own values.
    """
    with patch(f"{MODULE}._gc_apply._head_of", return_value=STUB_HEAD):
        yield


def decide_stale(
    worktree: Worktree,
    *,
    reachable: bool = True,
    staged: str = "clean",
    admin: str | None = "/a",
    present: bool = False,
) -> Decision:
    """Decide with the stale diagnostics stubbed to a clean, locatable entry.

    The diagnostics have their own tests in ``test_gc_stale_probes.py``. Pinning
    them here keeps these cases about the decision rather than about what the
    index happened to hold.

    ``present`` states whether the worktree directory is on disk. It is a
    parameter rather than a real ``stat`` so a case says what it means instead
    of depending on whether ``/gone/wt`` happens to be absent from the machine
    running the suite. It defaults to ``False`` because every worktree in these
    suites is stale.
    """
    with (
        patch(f"{MODULE}._gc_reasons.stale_head_is_reachable", return_value=reachable),
        patch(
            f"{MODULE}._gc_reasons._gc_stale.admin_dir_for",
            return_value=None if admin is None else Path(admin),
        ),
        patch(f"{MODULE}._gc_reasons._gc_stale.staged_content_state", return_value=staged),
    ):
        return decide(worktree, MAIN, BASE, cwds=frozenset(), checkout_present=lambda _: present)


def stale_worktree(
    path: str = "/gone/wt",
    *,
    branch: str | None = None,
    head: str | None = SHA,
    locked: bool = False,
    bare: bool = False,
    detached: bool = True,
    prunable: str | None = "gitdir file points to non-existent location",
) -> Worktree:
    """Build a stale-entry ``Worktree``, one field at a time.

    Spelled out rather than splatted from a dict so that a typo in a field name
    fails here instead of silently constructing a different worktree.
    """
    return Worktree(
        path=path,
        branch=branch,
        head=head,
        locked=locked,
        bare=bare,
        detached=detached,
        prunable=prunable,
    )
