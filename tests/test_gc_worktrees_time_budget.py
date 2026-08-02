"""Time-budget behaviour for the worktree GC reporter.

The reporter runs as a lefthook pre-push job under a timeout. Inspecting one
worktree costs up to three git subprocesses, so a large enough worktree set
pushes the run past that cap, lefthook kills it, and the push is rejected by a
report that mutates nothing and exits 0 on its own. These tests pin the budget
that keeps a report from deciding whether code can ship, the fail-safe invariant
that an uninspected worktree is never proposed for removal, and the refusal to
mutate anything from a partial report. The budget-to-cap relationship is pinned
in tests/ci/test_worktree_gc_wiring.py, which reads the cap from lefthook.yml.

Related: Issue #2761 (worktree accumulation), ADR-035 (exit codes)
"""

from __future__ import annotations

import threading
from unittest.mock import patch

from scripts.maintenance.gc_worktrees import (
    _DEFAULT_TIME_BUDGET_SECONDS,
    KEEP_MAIN,
    KEEP_TIME_BUDGET,
    Decision,
    GcReport,
    Worktree,
    apply_removals,
    build_report,
    format_report,
    main,
    parse_args,
)

_MAIN = "/repo"
_BASE = "origin/main"

# The deadline is tested before each worktree, so a run can start one last
# inspection just under it. That inspection makes at most three git calls,
# each capped at _GIT_TIMEOUT_SECONDS, and the job's own cap has to cover
# the sum or the budget buys nothing in the pathological case.


def _worktrees(count: int) -> list[Worktree]:
    """A main worktree plus ``count`` linked ones that are all safe to remove."""
    linked = [Worktree(path=f"/repo/wt{i}", branch=f"feat/{i}") for i in range(count)]
    return [Worktree(path=_MAIN, branch="main"), *linked]


class _Clock:
    """A fake monotonic clock that advances a fixed step per reading.

    Readings are serialized because the reporter now decides worktrees on a
    thread pool, so several workers call this concurrently. Without the lock
    the read-modify-write below loses increments under interleaving and the
    tests that count how many worktrees fell inside the deadline fail on a
    sample of runs rather than all of them. Measured before the lock: 7 of 12
    runs failed. The production clock is ``time.monotonic``, which needs no
    such protection; this is a fixture concern only.
    """

    def __init__(self, step: float = 0.0) -> None:
        self.now = 0.0
        self.step = step
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            current = self.now
            self.now += self.step
            return current


def _build(worktrees, *, time_budget, clock, apply=False):
    """Build a report with git fully mocked so only the budget varies."""
    with (
        patch(
            "scripts.maintenance.gc_worktrees.list_worktrees",
            return_value=worktrees,
        ),
        patch("scripts.maintenance.gc_worktrees._run_git", return_value=_MAIN),
        patch(
            "scripts.maintenance.gc_worktrees.has_uncommitted_changes",
            return_value=False,
        ),
        patch(
            "scripts.maintenance.gc_worktrees.is_merged_to_base",
            return_value=True,
        ),
    ):
        return build_report(base_ref=_BASE, apply=apply, time_budget=time_budget, clock=clock)


class TestTimeBudget:
    """build_report stops inspecting once the budget is spent."""

    def test_a_budget_that_is_never_spent_inspects_every_worktree(self):
        report = _build(_worktrees(3), time_budget=10.0, clock=_Clock(step=0.0))
        assert report.unevaluated == []
        assert [d.path for d in report.candidates] == [
            "/repo/wt0",
            "/repo/wt1",
            "/repo/wt2",
        ]

    def test_a_spent_budget_keeps_the_remaining_worktrees_unread(self):
        # Readings run 1, 2, 3 against a deadline of 3, so exactly one of the
        # two real worktrees lands inside it. Which one is not determinate:
        # decisions run on a thread pool, so the readings are handed out in
        # whatever order the workers pick items up. The budget still bounds the
        # work, and an unread worktree is still kept, which is what the caller
        # depends on. Asserting the identity here would pin an artifact of the
        # old serial loop and fail on roughly half of runs.
        report = _build(_worktrees(2), time_budget=3.0, clock=_Clock(step=1.0))
        assert len(report.candidates) == 1
        assert len(report.unevaluated) == 1
        assert report.unevaluated[0].reason == KEEP_TIME_BUDGET
        assert report.unevaluated[0].remove is False
        assert report.candidates[0].path != report.unevaluated[0].path
        assert {d.path for d in report.candidates} | {d.path for d in report.unevaluated} == {
            "/repo/wt0",
            "/repo/wt1",
        }

    def test_the_main_worktree_keeps_its_real_reason_past_the_deadline(self):
        # Structural checks cost no subprocess, so the budget must not blur
        # them into "not inspected".
        report = _build(_worktrees(2), time_budget=0.5, clock=_Clock(step=1.0))
        main_decision = next(d for d in report.decisions if d.path == _MAIN)
        assert main_decision.reason == KEEP_MAIN

    def test_an_uninspected_worktree_is_never_a_removal_candidate(self):
        # Every worktree here would otherwise be removable; the budget must not
        # let an uninspected one through into the candidate list.
        report = _build(_worktrees(4), time_budget=1.0, clock=_Clock(step=1.0))
        assert report.unevaluated, "expected the budget to truncate this run"
        candidates = {d.path for d in report.candidates}
        assert candidates.isdisjoint({d.path for d in report.unevaluated})

    def test_an_uninspected_worktree_costs_no_git_calls(self):
        clock = _Clock(step=1.0)
        with (
            patch(
                "scripts.maintenance.gc_worktrees.list_worktrees",
                return_value=_worktrees(3),
            ),
            patch("scripts.maintenance.gc_worktrees._run_git", return_value=_MAIN),
            patch(
                "scripts.maintenance.gc_worktrees.has_uncommitted_changes",
                return_value=False,
            ) as dirty_check,
            patch(
                "scripts.maintenance.gc_worktrees.is_merged_to_base",
                return_value=True,
            ),
        ):
            report = build_report(base_ref=_BASE, apply=False, time_budget=3.0, clock=clock)
        # main is structural (no git call), wt0 lands inside the deadline, and
        # wt1/wt2 fall outside it, so exactly one inspection should happen.
        assert len(report.unevaluated) == 2
        assert dirty_check.call_count == 1

    def test_a_budget_spent_before_the_first_worktree_inspects_none_of_them(self):
        report = _build(_worktrees(3), time_budget=0.5, clock=_Clock(step=1.0))
        assert report.candidates == []
        assert len(report.unevaluated) == 3

    def test_a_zero_budget_means_unlimited(self):
        report = _build(_worktrees(3), time_budget=0.0, clock=_Clock(step=1000.0))
        assert report.unevaluated == []
        assert len(report.candidates) == 3

    def test_a_negative_budget_means_unlimited(self):
        report = _build(_worktrees(3), time_budget=-1.0, clock=_Clock(step=1000.0))
        assert report.unevaluated == []

    def test_no_budget_means_unlimited(self):
        report = _build(_worktrees(3), time_budget=None, clock=_Clock(step=1000.0))
        assert report.unevaluated == []


class TestPartialReporting:
    """A truncated run says so instead of looking like a complete one."""

    def test_the_report_names_how_many_it_skipped(self):
        report = _build(_worktrees(3), time_budget=1.0, clock=_Clock(step=1.0))
        text = format_report(report)
        assert "PARTIAL" in text
        assert f"of {report.total_worktrees}" in text

    def test_a_complete_pass_says_nothing_about_a_budget(self):
        report = _build(_worktrees(3), time_budget=10.0, clock=_Clock(step=0.0))
        assert "PARTIAL" not in format_report(report)


class TestCli:
    """The CLI default has to fit inside the job that runs it."""

    def test_the_default_budget_applies_when_the_flag_is_absent(self):
        assert parse_args([]).time_budget == _DEFAULT_TIME_BUDGET_SECONDS

    def test_the_flag_overrides_the_default(self):
        assert parse_args(["--time-budget", "5"]).time_budget == 5.0

    def test_main_exits_zero_on_a_truncated_dry_run(self, capsys):
        truncated = _build(_worktrees(3), time_budget=1.0, clock=_Clock(step=1.0))
        assert truncated.unevaluated, "fixture must be a truncated report"
        with patch(
            "scripts.maintenance.gc_worktrees.build_report",
            return_value=truncated,
        ):
            code = main([])
        assert code == 0
        assert "PARTIAL" in capsys.readouterr().out

    def test_main_passes_the_budget_through_to_the_report(self):
        complete = _build(_worktrees(1), time_budget=None, clock=_Clock(step=0.0))
        with patch(
            "scripts.maintenance.gc_worktrees.build_report",
            return_value=complete,
        ) as builder:
            code = main(["--time-budget", "5"])
        assert code == 0
        assert builder.call_args.kwargs["time_budget"] == 5.0


class TestPartialReportsRefuseToMutate:
    """A truncated run must not remove or prune anything.

    A partial report describes whichever worktrees the clock allowed this run
    to inspect. Applying it would act on a different set than the dry run a
    reader reviewed, and ``git worktree prune`` would drop admin records for
    worktrees this run never looked at.
    """

    @staticmethod
    def _report(decisions: list[Decision]) -> GcReport:
        return GcReport(
            timestamp="t",
            base_ref="origin/main",
            apply=True,
            main_worktree="/repo",
            decisions=decisions,
        )

    def test_a_partial_report_removes_nothing(self):
        report = self._report(
            [
                Decision("/repo/a", "feat/a", remove=True, reason="merged to base"),
                Decision("/repo/z", "feat/z", remove=False, reason=KEEP_TIME_BUDGET),
            ]
        )
        with (
            patch("scripts.maintenance.gc_worktrees.remove_worktree") as remove,
            patch("scripts.maintenance.gc_worktrees.prune_worktrees") as prune,
        ):
            apply_removals(report)
        remove.assert_not_called()
        prune.assert_not_called()
        assert report.removed == []

    def test_a_partial_report_with_no_candidates_still_refuses_to_prune(self):
        """Q1: zero candidates does not make pruning safe on a partial report."""
        report = self._report(
            [Decision("/repo/z", "feat/z", remove=False, reason=KEEP_TIME_BUDGET)]
        )
        with (
            patch("scripts.maintenance.gc_worktrees.remove_worktree"),
            patch("scripts.maintenance.gc_worktrees.prune_worktrees") as prune,
        ):
            apply_removals(report)
        prune.assert_not_called()

    def test_the_refusal_names_the_remedy(self):
        report = self._report(
            [Decision("/repo/z", "feat/z", remove=False, reason=KEEP_TIME_BUDGET)]
        )
        with (
            patch("scripts.maintenance.gc_worktrees.remove_worktree"),
            patch("scripts.maintenance.gc_worktrees.prune_worktrees"),
        ):
            apply_removals(report)
        assert len(report.remove_errors) == 1
        message = report.remove_errors[0]
        assert "--time-budget 0" in message
        assert "1 worktree(s) were not inspected" in message

    def test_a_complete_report_is_not_refused(self):
        """Negative control: the guard must not fire on a full inspection."""
        report = self._report(
            [
                Decision("/repo/a", "feat/a", remove=True, reason="merged to base"),
                Decision("/repo/b", "feat/b", remove=False, reason=KEEP_MAIN),
            ]
        )
        with (
            patch("scripts.maintenance.gc_worktrees.remove_worktree") as remove,
            patch("scripts.maintenance.gc_worktrees.prune_worktrees") as prune,
        ):
            apply_removals(report)
        assert [c.args[0] for c in remove.call_args_list] == ["/repo/a"]
        prune.assert_called_once()
        assert report.remove_errors == []
