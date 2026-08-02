"""Occupancy guard for worktree GC.

A worktree can be clean, merged to base and fully pushed while an agent is
still working inside it. Removing it pulls the directory out from under a
running process. These tests pin the guard that keeps such a worktree, and
pin the containment rule that decides what "inside" means.
"""

from __future__ import annotations

from unittest.mock import patch

from scripts.maintenance.gc_worktrees import (
    KEEP_LOCKED,
    KEEP_MAIN,
    KEEP_OCCUPIED,
    KEEP_TIME_BUDGET,
    Worktree,
    build_report,
    decide,
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
                return_value=frozenset(),
            ) as spy,
        ):
            build_report(_BASE, apply=False)
        assert spy.call_count == 1


class TestProcScan:
    def test_a_missing_proc_filesystem_yields_no_occupancy(self):
        class _NoProc:
            def is_dir(self):
                return False

        with patch("scripts.maintenance.gc_worktrees.pathlib.Path", return_value=_NoProc()):
            assert occupied_paths() == frozenset()

    def test_the_live_scan_finds_this_process_own_directory(self):
        import os

        found = occupied_paths()
        assert os.getcwd() in found
