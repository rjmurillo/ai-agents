"""Typed result of the advisory temp-worktree gate (issue #5636).

The flipped assertion for the findings path lives beside the other gate tests in
``test_check_tmp_worktrees.py``; the remaining paths live here to keep that file
under the taste-lint size ceiling.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.validation import check_tmp_worktrees as checker
from scripts.validation.evidence import (
    REASON_ENTRIES_UNREADABLE,
    REASON_LISTING_FAILED,
    REASON_TREE_ABSENT,
    EvidenceState,
    pre_pr_policy,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _pin_free_bytes(monkeypatch: pytest.MonkeyPatch, free: int) -> None:
    """Make the free-space half of the scan independent of the test machine's disk."""
    usage = SimpleNamespace(total=free, used=0, free=free)
    monkeypatch.setattr(checker.shutil, "disk_usage", lambda path: usage)


def test_the_advisory_gate_passes_and_names_the_examined_count_when_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "plain-dir").mkdir()
    monkeypatch.setattr(checker, "DEFAULT_TEMP_ROOT", tmp_path)
    _pin_free_bytes(monkeypatch, 10 * 1024**3)

    outcome = checker.validate_tmp_worktrees(REPO_ROOT)

    assert outcome.state is EvidenceState.PASS
    assert outcome.examined == 1


def test_the_advisory_gate_skips_with_a_reason_when_the_temp_root_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checker, "DEFAULT_TEMP_ROOT", tmp_path / "missing")

    outcome = checker.validate_tmp_worktrees(REPO_ROOT)

    assert outcome.state is EvidenceState.SKIP
    assert outcome.reason == REASON_TREE_ABSENT
    # SKIP is licensed for every validator by the base policy's wildcard row, so
    # an absent temp root does not block the push.
    assert pre_pr_policy().accepts(outcome)


def test_a_failed_git_listing_is_blocked_not_a_clean_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checker, "DEFAULT_TEMP_ROOT", tmp_path)
    _pin_free_bytes(monkeypatch, 10 * 1024**3)
    monkeypatch.setattr(checker, "_list_registered", lambda repo_root: ([], True))

    outcome = checker.validate_tmp_worktrees(REPO_ROOT)

    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == REASON_LISTING_FAILED
    assert pre_pr_policy().accepts(outcome)


def test_an_unreadable_temp_root_is_blocked_not_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checker, "DEFAULT_TEMP_ROOT", tmp_path)
    monkeypatch.setattr(checker, "_is_directory", lambda path: None)

    outcome = checker.validate_tmp_worktrees(REPO_ROOT)

    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == REASON_ENTRIES_UNREADABLE
    assert pre_pr_policy().accepts(outcome)


def test_low_free_space_alone_is_an_advisory_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checker, "DEFAULT_TEMP_ROOT", tmp_path)
    _pin_free_bytes(monkeypatch, 0)

    outcome = checker.validate_tmp_worktrees(REPO_ROOT)

    assert outcome.state is EvidenceState.FAIL
    assert outcome.findings == 1


def test_an_absent_temp_root_with_a_failed_listing_is_blocked_not_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A SKIP would hide the failed listing behind the universal SKIP licence."""
    monkeypatch.setattr(checker, "DEFAULT_TEMP_ROOT", tmp_path / "missing")
    monkeypatch.setattr(checker, "_list_registered", lambda repo_root: ([], True))

    outcome = checker.validate_tmp_worktrees(REPO_ROOT)

    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == REASON_LISTING_FAILED


def test_unreadable_free_space_is_blocked_not_a_clean_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A gate that could not measure free space cannot claim it passed (PR #6065 review)."""
    (tmp_path / "plain").mkdir()
    monkeypatch.setattr(checker, "DEFAULT_TEMP_ROOT", tmp_path)

    def boom(_path: Path) -> None:
        raise OSError("statvfs failed")

    monkeypatch.setattr(checker.shutil, "disk_usage", boom)

    outcome = checker.validate_tmp_worktrees(REPO_ROOT)

    _check_blocked(outcome)


def test_an_unreadable_worktree_marker_is_blocked_not_a_clean_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "wt").mkdir()
    (tmp_path / "wt" / ".git").write_text("gitdir: /x/.git/worktrees/wt\n", encoding="utf-8")
    (tmp_path / "plain").mkdir()
    monkeypatch.setattr(checker, "DEFAULT_TEMP_ROOT", tmp_path)
    _pin_free_bytes(monkeypatch, 10 * 1024**3)
    real_open = Path.open

    def deny(self: Path, *args, **kwargs):
        if self.parent.name == "wt" and self.name == ".git":
            raise PermissionError("denied")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny)

    report = checker.build_report(REPO_ROOT)
    outcome = checker.validate_tmp_worktrees(REPO_ROOT)

    assert (report.unreadable_entries, report.examined) == (1, 1)
    _check_blocked(outcome)


def test_findings_still_outrank_an_unreadable_free_space_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "wt").mkdir()
    (tmp_path / "wt" / ".git").write_text("gitdir: /x/.git/worktrees/wt\n", encoding="utf-8")
    monkeypatch.setattr(checker, "DEFAULT_TEMP_ROOT", tmp_path)

    def boom(_path: Path) -> None:
        raise OSError("statvfs failed")

    monkeypatch.setattr(checker.shutil, "disk_usage", boom)

    outcome = checker.validate_tmp_worktrees(REPO_ROOT)

    assert outcome.state is EvidenceState.FAIL
    assert outcome.findings == 1


def _check_blocked(outcome: object) -> None:
    from scripts.validation.evidence import CheckOutcome

    assert isinstance(outcome, CheckOutcome)
    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == REASON_ENTRIES_UNREADABLE
    assert pre_pr_policy().accepts(outcome)
