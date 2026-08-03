"""Occupancy guard for worktree GC.

A worktree can be clean, merged to base and fully pushed while an agent is
still working inside it. Removing it pulls the directory out from under a
running process. These tests pin the guard that keeps such a worktree, and
pin the containment rule that decides what "inside" means.
"""

from __future__ import annotations

import errno
from types import SimpleNamespace
from unittest.mock import patch

from scripts.maintenance.gc_worktrees import (
    KEEP_LOCKED,
    KEEP_MAIN,
    KEEP_OCCUPIED,
    KEEP_TIME_BUDGET,
    GcReport,
    Occupancy,
    Worktree,
    build_report,
    decide,
    format_report,
    is_occupied,
    occupied_paths,
)

_MAIN = "/repo/main"
_BASE = "origin/main"


def _decide(path: str, cwds: frozenset[str], **kwargs) -> object:
    return decide(
        Worktree(path=path, branch="feat/x"),
        _MAIN,
        _BASE,
        cwds=cwds,
        **kwargs,
    )


class TestContainment:
    def test_a_process_sitting_exactly_in_the_worktree_counts(self):
        assert is_occupied("/repo/wt1", frozenset({"/repo/wt1"}))

    def test_a_process_in_a_subdirectory_counts(self):
        assert is_occupied("/repo/wt1", frozenset({"/repo/wt1/src/deep"}))

    def test_an_unrelated_directory_does_not_count(self):
        assert not is_occupied("/repo/wt1", frozenset({"/repo/other"}))

    def test_a_sibling_sharing_a_name_prefix_does_not_count(self):
        """`/repo/wt1` must not swallow `/repo/wt10`, a plain string prefix."""
        assert not is_occupied("/repo/wt1", frozenset({"/repo/wt10"}))

    def test_a_trailing_slash_on_the_worktree_path_is_tolerated(self):
        assert is_occupied("/repo/wt1/", frozenset({"/repo/wt1/src"}))

    def test_a_process_at_the_root_counts_even_with_a_trailing_slash(self):
        """The reported bug: a trailing slash made the root read as vacant.

        The sibling test above passes either way, because the sub-path branch
        strips the slash before comparing. Only the equality branch compared
        against the unstripped path, so a process sitting exactly at the
        worktree root was the one case a trailing slash could hide. Hiding it
        marks a worktree in active use as a deletion candidate.
        """
        assert is_occupied("/repo/wt1/", frozenset({"/repo/wt1"}))

    def test_a_trailing_slash_does_not_make_a_name_sibling_count(self):
        """Negative control for the normalization above.

        Stripping the slash must not degrade into a bare string prefix match,
        or `/repo/wt1/` would swallow `/repo/wt10`.
        """
        assert not is_occupied("/repo/wt1/", frozenset({"/repo/wt10"}))

    def test_no_live_processes_means_never_occupied(self):
        assert not is_occupied("/repo/wt1", frozenset())

    def test_the_parent_of_an_occupied_directory_counts_as_occupied(self):
        assert is_occupied("/repo", frozenset({"/repo/wt1"}))


class TestDecide:
    def test_an_occupied_worktree_is_kept(self):
        d = _decide("/repo/wt1", frozenset({"/repo/wt1"}))
        assert d.remove is False
        assert d.reason == KEEP_OCCUPIED

    def test_an_unoccupied_worktree_still_reaches_the_git_checks(self):
        """Negative control: without occupancy the guard must not intervene."""
        with (
            patch("scripts.maintenance.gc_worktrees.has_uncommitted_changes", return_value=False),
            patch("scripts.maintenance.gc_worktrees.is_merged_to_base", return_value=True),
        ):
            d = _decide("/repo/wt1", frozenset({"/repo/elsewhere"}))
        assert d.remove is True

    def test_occupancy_is_checked_without_running_git(self):
        """The guard must cost no subprocess, so it survives a truncated pass."""

        def _boom(*_a, **_k):
            raise AssertionError("git must not run for an occupied worktree")

        with (
            patch("scripts.maintenance.gc_worktrees.has_uncommitted_changes", _boom),
            patch("scripts.maintenance.gc_worktrees.is_merged_to_base", _boom),
        ):
            d = _decide("/repo/wt1", frozenset({"/repo/wt1"}))
        assert d.reason == KEEP_OCCUPIED

    def test_occupancy_outranks_the_time_budget_reason(self):
        """Even when the budget is spent, the real reason is still reported."""
        d = _decide("/repo/wt1", frozenset({"/repo/wt1"}), inspect=False)
        assert d.reason == KEEP_OCCUPIED

    def test_an_unoccupied_worktree_past_the_budget_reports_the_budget(self):
        d = _decide("/repo/wt1", frozenset(), inspect=False)
        assert d.reason == KEEP_TIME_BUDGET

    def test_the_main_worktree_keeps_its_own_reason_even_when_occupied(self):
        d = decide(
            Worktree(path=_MAIN, branch="main"),
            _MAIN,
            _BASE,
            cwds=frozenset({_MAIN}),
        )
        assert d.reason == KEEP_MAIN

    def test_a_locked_worktree_keeps_its_own_reason_even_when_occupied(self):
        d = decide(
            Worktree(path="/repo/wt1", branch="feat/x", locked=True),
            _MAIN,
            _BASE,
            cwds=frozenset({"/repo/wt1"}),
        )
        assert d.reason == KEEP_LOCKED


class TestReportInvariant:
    def test_an_occupied_worktree_is_never_a_removal_candidate(self):
        worktrees = [
            Worktree(path=_MAIN, branch="main"),
            Worktree(path="/repo/wt1", branch="feat/1"),
            Worktree(path="/repo/wt2", branch="feat/2"),
        ]
        with (
            patch("scripts.maintenance.gc_worktrees.list_worktrees", return_value=worktrees),
            patch("scripts.maintenance.gc_worktrees._run_git", return_value=_MAIN),
            patch("scripts.maintenance.gc_worktrees.has_uncommitted_changes", return_value=False),
            patch("scripts.maintenance.gc_worktrees.is_merged_to_base", return_value=True),
        ):
            report = build_report(_BASE, apply=False, cwds=frozenset({"/repo/wt1"}))

        paths = {c.path for c in report.candidates}
        assert "/repo/wt1" not in paths
        assert "/repo/wt2" in paths

    def test_detection_is_invoked_when_no_override_is_supplied(self):
        worktrees = [Worktree(path=_MAIN, branch="main")]
        with (
            patch("scripts.maintenance.gc_worktrees.list_worktrees", return_value=worktrees),
            patch("scripts.maintenance.gc_worktrees._run_git", return_value=_MAIN),
            patch(
                "scripts.maintenance.gc_worktrees.occupied_paths",
                return_value=Occupancy(frozenset(), 0),
            ) as spy,
        ):
            build_report(_BASE, apply=False)
        assert spy.call_count == 1


class TestProcScan:
    def test_a_missing_proc_filesystem_yields_no_occupancy(self):
        class _NoProc:
            def is_dir(self):
                return False

        with patch("scripts.maintenance.worktree_occupancy.pathlib.Path", return_value=_NoProc()):
            assert occupied_paths() == Occupancy(frozenset(), 0, proc_available=False)

    def test_a_missing_proc_filesystem_is_reported_as_unavailable(self):
        """An empty cwd set alone cannot distinguish "nobody home" from "never looked".

        Both produce `cwds=frozenset()` and `unreadable=0`, and the second one
        marks every worktree vacant. Since `gc_worktrees.py --apply` deletes
        what it marks, the two cases must be separable, and `unreadable` cannot
        do it: no entry was skipped because no entry was ever read.
        """

        class _NoProc:
            def is_dir(self):
                return False

        with patch("scripts.maintenance.worktree_occupancy.pathlib.Path", return_value=_NoProc()):
            assert occupied_paths().proc_available is False

    def test_a_real_scan_is_reported_as_available(self):
        """Negative control: the flag must not be False for every scan."""
        assert occupied_paths().proc_available is True

    def test_the_live_scan_finds_this_process_own_directory(self):
        import os

        found = occupied_paths().cwds
        assert os.getcwd() in found


class _FakeProcEntry:
    """One ``/proc/<pid>`` entry with a scripted readlink and stat outcome."""

    def __init__(self, name: str, *, cwd=None, link_errno=None, uid=None, stat_errno=None):
        self.name = name
        self.cwd = cwd
        self.link_errno = link_errno
        self.uid = uid
        self.stat_errno = stat_errno

    def __truediv__(self, _other):
        return self

    def stat(self):
        if self.stat_errno is not None:
            raise OSError(self.stat_errno, "stat refused")
        return SimpleNamespace(st_uid=self.uid)


def _scan(entries, *, uid=1000) -> Occupancy:
    """Run occupied_paths() against a synthetic /proc."""

    class _Proc:
        def is_dir(self):
            return True

        def iterdir(self):
            return iter(entries)

    def _readlink(entry):
        if entry.link_errno is not None:
            raise OSError(entry.link_errno, "readlink refused")
        return entry.cwd

    with (
        patch("scripts.maintenance.worktree_occupancy.pathlib.Path", return_value=_Proc()),
        patch("scripts.maintenance.worktree_occupancy.os.readlink", side_effect=_readlink),
        patch("scripts.maintenance.worktree_occupancy.os.getuid", return_value=uid),
    ):
        return occupied_paths()


class TestUnreadableProcessesAreNotVacancy:
    """An unreadable cwd is unknown, not proof that no process is there.

    Conflating the two is fail-open in a tool that deletes directories, so
    each error kind is pinned separately.
    """

    def test_a_readable_cwd_is_collected_and_counts_as_no_blind_spot(self):
        found = _scan([_FakeProcEntry("11", cwd="/repo/wt1", uid=1000)])
        assert found == Occupancy(frozenset({"/repo/wt1"}), 0)

    def test_permission_denied_on_our_own_process_is_counted_not_ignored(self):
        found = _scan([_FakeProcEntry("11", link_errno=errno.EACCES, uid=1000)])
        assert found.cwds == frozenset()
        assert found.unreadable == 1

    def test_a_process_that_exited_mid_scan_is_not_a_blind_spot(self):
        found = _scan([_FakeProcEntry("11", link_errno=errno.ENOENT, uid=1000)])
        assert found.unreadable == 0

    def test_a_reaped_pid_is_not_a_blind_spot(self):
        found = _scan([_FakeProcEntry("11", link_errno=errno.ESRCH, uid=1000)])
        assert found.unreadable == 0

    def test_another_users_process_is_not_counted_against_our_worktrees(self):
        found = _scan([_FakeProcEntry("11", link_errno=errno.EACCES, uid=0)])
        assert found.unreadable == 0

    def test_an_unattributable_process_is_not_counted(self):
        found = _scan([_FakeProcEntry("11", link_errno=errno.EACCES, stat_errno=errno.EACCES)])
        assert found.unreadable == 0

    def test_non_numeric_proc_entries_are_skipped(self):
        found = _scan([_FakeProcEntry("self", link_errno=errno.EACCES, uid=1000)])
        assert found == Occupancy(frozenset(), 0)

    def test_the_blind_spot_is_disclosed_in_the_human_report(self):
        report = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=False,
            main_worktree=_MAIN,
            occupancy_unreadable=3,
        )
        assert "occupancy blind spot: 3" in format_report(report)

    def test_no_blind_spot_prints_no_line(self):
        report = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=False,
            main_worktree=_MAIN,
            occupancy_unreadable=0,
        )
        assert "blind spot" not in format_report(report)

    def test_an_unavailable_scan_is_disclosed_in_the_human_report(self):
        """The silent case: no scan ran, so every worktree looks vacant.

        `occupancy_unreadable` stays 0 here because nothing was skipped, so the
        blind-spot line above never fires. Without its own disclosure the
        report would read exactly like a clean scan that found nobody home.
        """
        report = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=False,
            main_worktree=_MAIN,
            occupancy_unreadable=0,
            occupancy_unavailable=True,
        )
        assert "occupancy check unavailable" in format_report(report)

    def test_an_available_scan_prints_no_unavailability_line(self):
        """Negative control: the disclosure must not fire on every report."""
        report = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=False,
            main_worktree=_MAIN,
            occupancy_unreadable=0,
            occupancy_unavailable=False,
        )
        assert "occupancy check unavailable" not in format_report(report)
