"""Stale admin entries in worktree GC.

A worktree whose directory is gone leaves an admin entry behind. Every git
command run inside that directory fails, so the tool used to classify all 62
of them on this machine as "git inspection failed" and report KEEP, while
``--apply`` pruned them anyway. The dry-run plan contradicted what apply did.

These tests pin three things: that git's own ``prunable`` marker is what
decides staleness, that a stale entry whose HEAD no ref contains is kept
rather than pruned, and that a single unreachable entry withholds the prune
for all of them, because ``git worktree prune`` takes no path argument.
"""

from __future__ import annotations

from unittest.mock import patch

from scripts.maintenance.gc_worktrees import (
    KEEP_LOCKED,
    KEEP_MAIN,
    KEEP_STALE_UNREACHABLE,
    KEEP_TIME_BUDGET,
    PRUNE_STALE,
    Decision,
    GcReport,
    Worktree,
    apply_removals,
    decide,
    list_worktrees,
    stale_head_is_reachable,
)

_MAIN = "/repo/main"
_BASE = "origin/main"
_SHA = "f30c6952bf2da328bcff0aecc74ff05de3558df7"

_MODULE = "scripts.maintenance.gc_worktrees"


def _decide(worktree: Worktree, *, reachable: bool = True) -> Decision:
    with patch(f"{_MODULE}.stale_head_is_reachable", return_value=reachable):
        return decide(worktree, _MAIN, _BASE, cwds=frozenset())


def _parse(text: str) -> list[Worktree]:
    """Run the real porcelain parser over canned ``git worktree list`` output."""
    with patch(f"{_MODULE}._run_git", return_value=text):
        return list_worktrees()


def _stale(path: str = "/gone/wt", **kwargs) -> Worktree:
    fields = {
        "branch": None,
        "head": _SHA,
        "detached": True,
        "prunable": "gitdir file points to non-existent location",
    }
    fields.update(kwargs)
    return Worktree(path=path, **fields)


class TestPorcelainParsing:
    """``prunable`` is a real porcelain line and must survive the parser."""

    def test_a_prunable_line_with_a_reason_is_captured(self):
        text = (
            f"worktree /gone/wt\nHEAD {_SHA}\ndetached\n"
            "prunable gitdir file points to non-existent location\n\n"
        )
        (worktree,) = _parse(text)
        assert worktree.prunable == "gitdir file points to non-existent location"

    def test_a_bare_prunable_line_still_marks_the_entry(self):
        text = f"worktree /gone/wt\nHEAD {_SHA}\ndetached\nprunable\n\n"
        (worktree,) = _parse(text)
        assert worktree.prunable == "prunable"

    def test_a_healthy_worktree_has_no_prunable_marker(self):
        text = f"worktree /repo/wt\nHEAD {_SHA}\nbranch refs/heads/feat/x\n\n"
        (worktree,) = _parse(text)
        assert worktree.prunable is None

    def test_prunable_does_not_leak_into_the_branch_field(self):
        text = f"worktree /gone/wt\nHEAD {_SHA}\ndetached\nprunable whatever\n\n"
        (worktree,) = _parse(text)
        assert worktree.branch is None


class TestDecide:
    """Staleness is decided from git's marker, not from a filesystem probe."""

    def test_a_stale_entry_whose_head_is_reachable_is_a_prune_candidate(self):
        decision = _decide(_stale(), reachable=True)
        assert decision.remove is True
        assert decision.reason == PRUNE_STALE

    def test_a_stale_entry_whose_head_is_unreachable_is_kept(self):
        decision = _decide(_stale(), reachable=False)
        assert decision.remove is False
        assert decision.reason.startswith(KEEP_STALE_UNREACHABLE)

    def test_the_kept_reason_carries_the_sha_needed_to_rescue_it(self):
        """A path alone is not actionable; the rescue command needs the SHA."""
        decision = _decide(_stale(), reachable=False)
        assert f"git branch <name> {_SHA}" in decision.reason

    def test_a_stale_entry_past_the_time_budget_costs_no_reachability_call(self):
        """The budget guard must precede the subprocess the check spawns."""
        with patch(f"{_MODULE}.stale_head_is_reachable") as reachable:
            decision = decide(
                _stale(), _MAIN, _BASE, cwds=frozenset(), inspect=False
            )
        reachable.assert_not_called()
        assert decision.reason == KEEP_TIME_BUDGET
        assert decision.remove is False

    def test_a_stale_entry_never_reaches_the_git_inspection_path(self):
        """The old code ran git in a directory that no longer exists.

        Any git call from ``decide`` on a stale entry is the regression this
        test exists to catch, so the runner raises instead of returning.
        """

        def explode(*_args, **_kwargs):
            raise AssertionError("decide ran git inside a missing worktree")

        with patch(f"{_MODULE}._run_git", side_effect=explode):
            decision = _decide(_stale(), reachable=True)
        assert decision.reason == PRUNE_STALE

    def test_a_locked_stale_entry_stays_locked(self):
        decision = _decide(_stale(locked=True), reachable=True)
        assert decision.reason == KEEP_LOCKED

    def test_the_main_worktree_wins_even_if_git_calls_it_prunable(self):
        decision = _decide(_stale(path=_MAIN), reachable=True)
        assert decision.reason == KEEP_MAIN

    def test_a_stale_entry_on_a_branch_keeps_its_branch_in_the_decision(self):
        decision = _decide(_stale(branch="feat/x", detached=False), reachable=True)
        assert decision.branch == "feat/x"


class TestReachability:
    """The guard fails safe: anything it cannot confirm counts as unreachable."""

    def test_a_head_contained_by_a_ref_is_reachable(self):
        with patch(f"{_MODULE}._run_git", return_value="refs/heads/main\n"):
            assert stale_head_is_reachable(_SHA) is True

    def test_a_head_no_ref_contains_is_unreachable(self):
        with patch(f"{_MODULE}._run_git", return_value="\n"):
            assert stale_head_is_reachable(_SHA) is False

    def test_a_git_failure_counts_as_unreachable(self):
        with patch(f"{_MODULE}._run_git", side_effect=RuntimeError("boom")):
            assert stale_head_is_reachable(_SHA) is False

    def test_a_missing_head_counts_as_unreachable(self):
        assert stale_head_is_reachable(None) is False
        assert stale_head_is_reachable("") is False

    def test_a_missing_head_costs_no_git_call(self):
        with patch(f"{_MODULE}._run_git") as runner:
            stale_head_is_reachable(None)
        runner.assert_not_called()


def _report(*decisions: Decision) -> GcReport:
    return GcReport(
        timestamp="2026-08-05T00:00:00Z",
        base_ref=_BASE,
        apply=True,
        main_worktree=_MAIN,
        total_worktrees=len(decisions),
        decisions=list(decisions),
    )


def _prune_stale(path: str) -> Decision:
    return Decision(path, None, remove=True, reason=PRUNE_STALE)


def _keep_unreachable(path: str) -> Decision:
    return Decision(path, None, remove=False, reason=KEEP_STALE_UNREACHABLE)


class TestNoBlanketPrune:
    """The data-loss path this change removed must not come back.

    ``git worktree prune`` takes no path argument, so it drops every entry git
    considers prunable: entries that went stale after the plan was built, and
    entries this tool deliberately held back because no ref contains their
    HEAD. ``git worktree remove`` works on a stale entry, so per-path removal
    covers the same ground without that reach.
    """

    def test_the_module_exposes_no_blanket_prune_helper(self):
        import scripts.maintenance.gc_worktrees as module

        assert not hasattr(module, "prune_worktrees")

    def test_apply_never_shells_out_to_worktree_prune(self):
        report = _report(_prune_stale("/gone/a"))
        calls: list[list[str]] = []

        def record(args, **_kwargs):
            calls.append(args)
            return ""

        with patch(f"{_MODULE}._run_git", side_effect=record):
            apply_removals(report)
        assert not any("prune" in c for c in calls), calls


class TestApply:
    """Stale entries are removed per path, like any other candidate."""

    def test_a_stale_candidate_goes_through_remove_worktree(self):
        report = _report(_prune_stale("/gone/a"))
        with patch(f"{_MODULE}.remove_worktree") as remove:
            apply_removals(report)
        remove.assert_called_once_with("/gone/a")
        assert report.removed == ["/gone/a"]

    def test_a_kept_unreachable_entry_is_never_touched(self):
        report = _report(_prune_stale("/gone/a"), _keep_unreachable("/gone/b"))
        with patch(f"{_MODULE}.remove_worktree") as remove:
            apply_removals(report)
        assert [c.args[0] for c in remove.call_args_list] == ["/gone/a"]
        assert "/gone/b" not in report.removed

    def test_one_unsafe_entry_does_not_block_the_safe_ones(self):
        """The withheld-prune design punished 61 safe entries for 1 unsafe one."""
        report = _report(
            _keep_unreachable("/gone/x"),
            *(_prune_stale(f"/gone/{i}") for i in range(5)),
        )
        with patch(f"{_MODULE}.remove_worktree"):
            apply_removals(report)
        assert report.removed == [f"/gone/{i}" for i in range(5)]

    def test_a_failed_removal_is_recorded_and_not_claimed_as_removed(self):
        report = _report(_prune_stale("/gone/a"), _prune_stale("/gone/b"))

        def fail_on_a(path: str) -> None:
            if path == "/gone/a":
                raise RuntimeError("still locked")

        with patch(f"{_MODULE}.remove_worktree", side_effect=fail_on_a):
            apply_removals(report)
        assert report.removed == ["/gone/b"]
        assert any("/gone/a" in e and "still locked" in e for e in report.remove_errors)

    def test_a_live_candidate_and_a_stale_one_take_the_same_path(self):
        live = Decision("/repo/wt", "feat/x", remove=True, reason="fully pushed")
        report = _report(live, _prune_stale("/gone/a"))
        with patch(f"{_MODULE}.remove_worktree") as remove:
            apply_removals(report)
        assert [c.args[0] for c in remove.call_args_list] == ["/repo/wt", "/gone/a"]


class TestPlanMatchesApply:
    """The contract the old code broke: the plan must predict what apply does."""

    def test_apply_removes_exactly_the_paths_the_plan_named(self):
        report = _report(
            _prune_stale("/gone/a"),
            _prune_stale("/gone/b"),
            _keep_unreachable("/gone/c"),
            Decision("/repo/d", "feat/d", remove=False, reason="uncommitted changes"),
        )
        planned = [d.path for d in report.candidates]
        with patch(f"{_MODULE}.remove_worktree"):
            apply_removals(report)
        assert report.removed == planned

    def test_a_kept_stale_entry_is_not_listed_as_a_candidate(self):
        report = _report(_keep_unreachable("/gone/b"))
        assert report.candidates == []
        assert [d.path for d in report.kept] == ["/gone/b"]
