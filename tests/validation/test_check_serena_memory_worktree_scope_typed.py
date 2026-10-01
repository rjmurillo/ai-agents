"""Typed result of the advisory Serena memory scope gate for an unreadable sibling.

Kept apart from ``test_check_serena_memory_worktree_scope.py`` to hold that file
under the taste-lint size ceiling (issue #5636).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_serena_memory_worktree_scope as checker

from scripts.validation.evidence import (
    REASON_ENTRIES_UNREADABLE,
    EvidenceState,
    pre_pr_policy,
)


def test_an_unreadable_sibling_is_blocked_not_a_clean_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        checker,
        "build_scope_report",
        lambda root: checker.ScopeReport(
            current_worktree=str(root), other_worktrees_examined=1, unreadable_worktrees=1
        ),
    )

    outcome = checker.validate_serena_memory_worktree_scope(tmp_path)

    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == REASON_ENTRIES_UNREADABLE
    assert pre_pr_policy().accepts(outcome)
