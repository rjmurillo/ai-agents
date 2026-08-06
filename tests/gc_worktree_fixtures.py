"""Shared fixtures for the worktree GC suites that name synthetic paths.

Three suites drive ``decide`` against fabricated worktree paths. They import
these stubs from here rather than each carrying a copy, so the reason each one
exists is written down once and cannot drift between them.

Both stubs answer a probe that reads the real filesystem. Against a path that
was never created, the honest answer is "unknown" or "gone", and both keep
every worktree, which would leave these suites asserting nothing. So each stub
declares the fabricated path stands for a healthy worktree, and the probe it
replaces is measured against real git instead.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest

_PROBE = "scripts.maintenance.gc_worktrees._gc_reasons.reflog_only_work"
_PRESENT = "scripts.maintenance.gc_worktrees._gc_stale.linked_checkout_present"


@pytest.fixture(autouse=True)
def checkout_is_present() -> Iterator[None]:
    """Declare that every fabricated path holds its own checkout.

    ``decide`` calls ``is_stale`` before any merge check, and staleness is not
    ``prunable`` alone: an entry whose ``.git`` marker is missing, or present
    but naming another worktree's admin directory, is stale even when git says
    nothing. A fabricated path carries no marker at all, so without this stub
    every worktree in these suites would report as a stale entry.

    What the stub replaces is covered where it can be measured:
    ``TestCheckoutPresence`` in ``test_gc_worktrees_stale.py`` builds the file
    layout and states each answer, and
    ``test_gc_worktrees_real_git_stale.py`` proves against real git that a
    worktree moved onto another's deleted path does not make that entry
    healthy.
    """
    with patch(_PRESENT, return_value=True):
        yield


@pytest.fixture(autouse=True)
def no_reflog_only_work() -> Iterator[None]:
    """Stub the reflog probe to "nothing would be orphaned".

    ``decide`` asks whether removing a candidate would orphan commits that the
    worktree's own reflog alone anchors. Against a fabricated path that probe
    cannot find an admin directory, answers "unknown", and keeps every
    worktree, which would hide what these suites are about.

    The gate itself is covered where it can be measured: in
    ``test_gc_worktrees_stale.py`` for the reason text, and against real git in
    ``test_gc_worktrees_real_git_healthy.py``, which proves both that a
    reflog-only commit keeps its worktree and that a worktree with nothing at
    risk is still removed.
    """
    with patch(_PROBE, return_value=""):
        yield
