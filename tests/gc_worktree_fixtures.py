"""Shared fixtures for the worktree GC suites that name synthetic paths.

Three suites drive ``decide`` against fabricated worktree paths. They import
``no_reflog_only_work`` from here rather than each carrying a copy, so the
reason the stub exists is written down once and cannot drift between them.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest

_PROBE = "scripts.maintenance.gc_worktrees._gc_reasons.reflog_only_work"


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
