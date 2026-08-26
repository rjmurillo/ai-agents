"""Fixtures for the ADR debate-log mutation harness.

`scratch_worktree` lives here rather than in `_adr_debate_harness.py` because a
fixture has to be discoverable by pytest, and importing one by name into the
test module is fragile: it reads as an unused import, and `ruff check --fix`
duly deleted it, which turned every mutant into a setup error. A conftest is
the form that cannot be linted away.

Issue #5205.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.testing.mutation_workspace import isolated_mutation_worktree
from tests.mutation._adr_debate_harness import _TARGET_REL, REPO_ROOT


@pytest.fixture()
def scratch_worktree() -> Iterator[Path]:
    """Provide a marked scratch git worktree; remove it after the test."""
    with isolated_mutation_worktree(REPO_ROOT, [_TARGET_REL]) as workspace:
        yield workspace.root
