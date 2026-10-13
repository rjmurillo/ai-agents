"""Directories another user owns do not make the temp-worktree gate BLOCKED (issue #6487).

On a host running systemd or snapd, `/tmp` holds root-owned mode 0700 directories. The marker stat
inside them raises ``PermissionError`` for every other user, so the gate reported
``entries.unreadable`` on every run. Tests that need a foreign
owner fake it through ``os.getuid`` or ``is_foreign_owned``, so they pass for any
user, including root.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.validation import check_tmp_worktrees as checker
from scripts.validation.evidence import REASON_ENTRIES_UNREADABLE, EvidenceState

REPO_ROOT = Path(__file__).resolve().parents[2]
_GIB = 1024**3


def _pin_free_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    usage = SimpleNamespace(total=10 * _GIB, used=0, free=10 * _GIB)
    monkeypatch.setattr(checker.shutil, "disk_usage", lambda path: usage)


def _lock_markers(monkeypatch: pytest.MonkeyPatch, *dir_names: str) -> None:
    """Make the `.git` stat inside the named directories fail with EACCES."""
    real_stat = Path.stat

    def deny(self: Path, *args, **kwargs):
        if self.name == ".git" and self.parent.name in dir_names:
            raise PermissionError("denied")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", deny)


def _act_as_another_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every directory in the fixture look owned by someone else."""
    other = getattr(os, "getuid", lambda: 0)() + 1
    monkeypatch.setattr(checker.os, "getuid", lambda: other, raising=False)


def test_a_locked_directory_owned_by_another_user_is_disclosed_not_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "systemd-private-x").mkdir()
    (tmp_path / "plain").mkdir()
    monkeypatch.setattr(checker, "DEFAULT_TEMP_ROOT", tmp_path)
    _pin_free_bytes(monkeypatch)
    _lock_markers(monkeypatch, "systemd-private-x")
    _act_as_another_user(monkeypatch)

    report = checker.build_report(REPO_ROOT)
    outcome = checker.validate_tmp_worktrees(REPO_ROOT)

    assert (report.unreadable_entries, report.foreign_entries, report.examined) == (0, 1, 1)
    assert outcome.state is not EvidenceState.BLOCKED


def test_the_report_names_the_foreign_owned_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "systemd-private-x").mkdir()
    _pin_free_bytes(monkeypatch)
    _lock_markers(monkeypatch, "systemd-private-x")
    _act_as_another_user(monkeypatch)

    report = checker.scan_temp_root(tmp_path, 0, [], git_listing_failed=False)
    text = checker.format_report(report)

    assert "1 entry/entries" in text
    assert "owned by another user" in text
    assert "were unreadable" not in text


def test_a_locked_directory_the_current_user_owns_stays_unreadable_and_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "mine-locked").mkdir()
    monkeypatch.setattr(checker, "DEFAULT_TEMP_ROOT", tmp_path)
    _pin_free_bytes(monkeypatch)
    _lock_markers(monkeypatch, "mine-locked")

    report = checker.build_report(REPO_ROOT)
    outcome = checker.validate_tmp_worktrees(REPO_ROOT)

    assert (report.unreadable_entries, report.foreign_entries) == (1, 0)
    assert report.unreadable_paths == [str(tmp_path / "mine-locked")]
    assert f"unreadable: {tmp_path / 'mine-locked'}" in checker.format_report(report)
    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == REASON_ENTRIES_UNREADABLE


def test_foreign_and_own_locked_directories_are_counted_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "theirs").mkdir()
    (tmp_path / "mine").mkdir()
    _pin_free_bytes(monkeypatch)
    _lock_markers(monkeypatch, "theirs", "mine")
    monkeypatch.setattr(checker, "is_foreign_owned", lambda p: p.name == "theirs")

    report = checker.scan_temp_root(tmp_path, 0, [], git_listing_failed=False)

    assert (report.unreadable_entries, report.foreign_entries) == (1, 1)
    assert report.unreadable_paths == [str(tmp_path / "mine")]


def test_a_readable_worktree_is_reported_whoever_owns_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: /x/.git/worktrees/wt\n", encoding="utf-8")
    _pin_free_bytes(monkeypatch)
    _act_as_another_user(monkeypatch)

    report = checker.scan_temp_root(tmp_path, 0, [], git_listing_failed=False)

    assert [w.path for w in report.worktrees] == [str(wt)]
    assert report.foreign_entries == 0


def test_a_platform_without_getuid_never_treats_an_entry_as_foreign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(checker.os, "getuid", raising=False)

    assert checker.is_foreign_owned(tmp_path) is False


def test_an_entry_that_cannot_be_statted_is_not_foreign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_stat = Path.stat

    def deny(self: Path, *args, **kwargs):
        if self == tmp_path:
            raise PermissionError("denied")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", deny)

    assert checker.is_foreign_owned(tmp_path) is False


def test_is_foreign_owned_compares_the_owner_uid_with_the_process_uid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = tmp_path.stat().st_uid
    monkeypatch.setattr(checker.os, "getuid", lambda: owner, raising=False)
    assert checker.is_foreign_owned(tmp_path) is False
    monkeypatch.setattr(checker.os, "getuid", lambda: owner + 1, raising=False)
    assert checker.is_foreign_owned(tmp_path) is True


def test_unreadable_paths_are_capped_in_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = [f"locked{i}" for i in range(8)]
    for name in names:
        (tmp_path / name).mkdir()
    _pin_free_bytes(monkeypatch)
    _lock_markers(monkeypatch, *names)

    report = checker.scan_temp_root(tmp_path, 0, [], git_listing_failed=False)
    lines = checker.format_report(report).splitlines()

    assert report.unreadable_entries == 8
    assert sum(1 for line in lines if line.startswith("  unreadable: ")) == 5
    assert "  ... and 3 more" in lines
