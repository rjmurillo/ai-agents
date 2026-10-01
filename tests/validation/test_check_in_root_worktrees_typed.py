"""Typed result of the advisory in-root worktree gate for unreadable observations.

Kept apart from ``test_check_in_root_worktrees.py`` to hold that file under the
taste-lint size ceiling (issue #5636, PR #6065 review). Each case makes one read
fail the way an EACCES does and asserts the gate does not report a clean pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import check_in_root_worktrees as checker
from scripts.validation.evidence import (
    REASON_ENTRIES_UNREADABLE,
    EvidenceState,
    pre_pr_policy,
)


def _worktree_dir(parent: Path, name: str) -> Path:
    """A directory holding the `.git` file `git worktree add` writes."""
    wt = parent / name
    wt.mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: /x/.git/worktrees/{name}\n", encoding="utf-8")
    return wt


def test_an_unreadable_marker_is_counted_not_examined_and_blocks_a_clean_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory whose `.git` cannot be read was not inspected (PR #6065 review)."""
    _worktree_dir(tmp_path / ".claude/worktrees", "wt")
    (tmp_path / ".claude/worktrees" / "plain").mkdir()
    monkeypatch.setattr(checker, "_list_registered", lambda repo_root: ([], False))
    real_open = Path.open

    def deny(self: Path, *args, **kwargs):
        if self.parent.name == "wt" and self.name == ".git":
            raise PermissionError("denied")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny)

    report = checker.build_report(tmp_path)
    outcome = checker.validate_in_root_worktrees(tmp_path)

    # The ".claude" container and "plain" were examined; "wt" was not.
    assert (report.unreadable_entries, report.examined) == (1, 2)
    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == REASON_ENTRIES_UNREADABLE
    assert pre_pr_policy().accepts(outcome)


def _deny_stat(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    real_stat = Path.stat

    def deny(self: Path, *args, **kwargs):
        if self.name in names:
            raise PermissionError("denied")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", deny)


def test_an_unreadable_container_is_counted_not_read_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Path.is_dir swallows the error on 3.14, so a locked container vanished silently."""
    (tmp_path / ".claude/worktrees").mkdir(parents=True)
    monkeypatch.setattr(checker, "_list_registered", lambda repo_root: ([], False))
    _deny_stat(monkeypatch, "worktrees")

    report = checker.build_report(tmp_path)
    outcome = checker.validate_in_root_worktrees(tmp_path)

    assert report.unreadable_entries >= 1
    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == REASON_ENTRIES_UNREADABLE


def test_an_unreadable_child_directory_is_counted_not_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".claude/worktrees" / "ok").mkdir(parents=True)
    (tmp_path / ".claude/worktrees" / "locked").mkdir()
    monkeypatch.setattr(checker, "_list_registered", lambda repo_root: ([], False))
    _deny_stat(monkeypatch, "locked")

    report = checker.build_report(tmp_path)

    assert report.unreadable_entries == 1
