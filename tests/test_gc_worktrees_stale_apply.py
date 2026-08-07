"""What ``--apply`` does with a plan that contains stale entries.

The plan is not the act. ``apply_removals`` re-reads the repository, re-checks
each candidate's HEAD, and stops on the first failure, so a worktree that
changed between the plan and the act is left alone. These tests pin that the
two agree, and that no blanket ``git worktree prune`` is ever recommended or
run: it takes no path argument, so it would clear every sibling entry too.

What the plan says in the first place is tested in
``test_gc_worktrees_stale.py``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.maintenance import _gc_apply, _gc_parse
from scripts.maintenance.gc_worktrees import (
    KEEP_TIME_BUDGET,
    Decision,
    GcReport,
    Worktree,
    decide,
)
from scripts.maintenance.worktree_report import KEEP_STALE, KEEP_STALE_UNREACHABLE

_MAIN = "/repo/main"
_BASE = "origin/main"
_SHA = "f30c6952bf2da328bcff0aecc74ff05de3558df7"

_MODULE = "scripts.maintenance.gc_worktrees"


_STUB_HEAD = "f" * 40


def _forbidden_git(*_args: str) -> str:
    """Fail loudly if a mocked apply reaches real git.

    Every apply test in this module patches the mutating helpers, so
    ``run_git`` should never be called. A stub that raises turns a lost patch
    seam into an immediate failure instead of a real subprocess against the
    developer's own repository.
    """
    raise AssertionError("apply_removals reached real git in a mocked test")


@pytest.fixture(autouse=True)
def _stub_pre_removal_probes():
    """Unit tests name paths that do not exist, so both pre-removal reads are stubbed.

    ``apply_removals`` asks two questions immediately before each removal:
    whether the worktree's HEAD is still where the recheck decision recorded
    it, and whether its reflog has since become the only anchor for a commit.
    Both read the filesystem, both fail against a fabricated path, and either
    failure withholds every removal, which would hide what these tests are
    about. Tests that care about a comparison patch it again with their own
    values.

    What the stubs replace is measured in
    ``test_gc_worktrees_real_git_apply.py``, which builds both races against
    real git and reads the object database back.
    """
    with (
        patch(f"{_MODULE}._gc_apply._head_of", return_value=_STUB_HEAD),
        patch(f"{_MODULE}._gc_reasons.reflog_only_work", return_value=""),
    ):
        yield


def _decide(
    worktree: Worktree,
    *,
    reachable: bool = True,
    staged: str = "clean",
    admin: str | None = "/a",
    present: bool = False,
) -> Decision:
    """Decide with the stale diagnostics stubbed to a clean, locatable entry.

    The diagnostics have their own tests below. Pinning them here keeps these
    cases about the decision rather than about what the index happened to hold.

    ``present`` states whether the worktree directory is on disk. It is a
    parameter rather than a real ``stat`` so a case says what it means instead
    of depending on whether ``/gone/wt`` happens to be absent from the machine
    running the suite. It defaults to ``False`` because every worktree in this
    file is stale.
    """
    with (
        patch(f"{_MODULE}._gc_reasons.stale_head_is_reachable", return_value=reachable),
        patch(
            f"{_MODULE}._gc_reasons._gc_stale.admin_dir_for",
            return_value=None if admin is None else Path(admin),
        ),
        patch(f"{_MODULE}._gc_reasons._gc_stale.staged_content_state", return_value=staged),
    ):
        return decide(worktree, _MAIN, _BASE, cwds=frozenset(), checkout_present=lambda _: present)


def _parse(text: str) -> list[Worktree]:
    """Run the real porcelain parser over canned ``git worktree list`` output."""
    return _gc_parse.list_worktrees(lambda _: text)


def _stale(
    path: str = "/gone/wt",
    *,
    branch: str | None = None,
    head: str | None = _SHA,
    locked: bool = False,
    bare: bool = False,
    detached: bool = True,
    prunable: str | None = "gitdir file points to non-existent location",
) -> Worktree:
    """Build a stale-entry ``Worktree``, one field at a time.

    Spelled out rather than splatted from a dict so that a typo in a field
    name fails here instead of silently constructing a different worktree.
    """
    return Worktree(
        path=path,
        branch=branch,
        head=head,
        locked=locked,
        bare=bare,
        detached=detached,
        prunable=prunable,
    )


def _report(*decisions: Decision) -> GcReport:
    return GcReport(
        timestamp="2026-08-05T00:00:00Z",
        base_ref=_BASE,
        apply=True,
        main_worktree=_MAIN,
        total_worktrees=len(decisions),
        decisions=list(decisions),
    )


def _live(path: str, branch: str | None = "feat/x") -> Decision:
    """A candidate the plan proposes removing.

    ``head`` is what ``--apply`` compares against just before it removes. A
    removal decision that carries none is refused, because nothing then
    establishes the worktree is where the recheck left it, so a candidate
    without one cannot stand in for a real plan here.
    """
    return Decision(path, branch, remove=True, reason="fully pushed", head=_STUB_HEAD)


def _keep_unreachable(path: str) -> Decision:
    return Decision(path, None, remove=False, reason=KEEP_STALE_UNREACHABLE)


def _keep_stale(path: str) -> Decision:
    return Decision(path, None, remove=False, reason=KEEP_STALE)


def _agrees(report: GcReport):
    """A recheck that reproduces the plan, i.e. nothing changed underneath it."""
    return lambda: _report(*report.decisions)


class TestNoBlanketPrune:
    """The data-loss path this change removed must not come back.

    ``git worktree prune`` takes no path argument, so it drops every entry git
    considers prunable: entries that went stale after the plan was built, and
    entries this tool deliberately held back because no ref contains their
    HEAD. Removal is per path or it does not happen.
    """

    def test_the_module_exposes_no_blanket_prune_helper(self):
        import scripts.maintenance.gc_worktrees as module

        assert not hasattr(module, "prune_worktrees")

    def test_apply_never_shells_out_to_worktree_prune(self):
        report = _report(_live("/repo/a"))
        calls: list[list[str]] = []

        def record(args, **_kwargs):
            calls.append(args)
            return ""

        _gc_apply.apply_removals(report, revalidate=_agrees(report), run_git=record)
        assert not any("prune" in c for c in calls), calls


class TestPerCandidateHead:
    """Removals run in series, so the last candidate acts on a seconds-old plan.

    ``git worktree remove`` refuses a dirty tree but accepts a *committed*
    change, so a commit landing between the recheck and this candidate's own
    turn is removed and orphaned. Re-reading each HEAD immediately before its
    own removal narrows that window to a single subprocess.

    What it is compared against has to be the HEAD the recheck decided on,
    which each removal decision carries. Reading the baseline separately, after
    the recheck returned, meant a commit landing between those two reads became
    the baseline and then matched itself.
    """

    def test_a_head_that_moved_after_the_recheck_withholds_that_removal(self):
        report = _report(_live("/repo/a"), _live("/repo/b"))
        moved = {"/repo/a": _STUB_HEAD, "/repo/b": "9" * 40}

        with patch(f"{_MODULE}._gc_apply._head_of", side_effect=lambda p, _g: moved[p]):
            with patch(f"{_MODULE}._gc_apply.remove_worktree") as remove:
                _gc_apply.apply_removals(report, revalidate=lambda: report, run_git=_forbidden_git)
        assert [c.args[0] for c in remove.call_args_list] == ["/repo/a"]
        assert any("/repo/b" in e and "HEAD moved" in e for e in report.remove_errors)

    def test_an_unreadable_head_is_not_evidence_of_safety(self):
        report = _report(_live("/repo/a"))
        with patch(f"{_MODULE}._gc_apply._head_of", return_value=None):
            with patch(f"{_MODULE}._gc_apply.remove_worktree") as remove:
                _gc_apply.apply_removals(report, revalidate=lambda: report, run_git=_forbidden_git)
        remove.assert_not_called()
        assert any("could not be read" in e for e in report.remove_errors)

    def test_a_recheck_that_recorded_no_head_leaves_nothing_to_compare(self):
        report = _report(Decision("/repo/a", "feat/a", remove=True, reason="fully pushed"))
        with patch(f"{_MODULE}._gc_apply.remove_worktree") as remove:
            _gc_apply.apply_removals(report, revalidate=lambda: report, run_git=_forbidden_git)
        remove.assert_not_called()
        assert any("recorded no HEAD" in e for e in report.remove_errors)

    def test_an_unchanged_head_does_not_block_the_removal(self):
        report = _report(_live("/repo/a"))
        with patch(f"{_MODULE}._gc_apply._head_of", return_value=_STUB_HEAD):
            with patch(f"{_MODULE}._gc_apply.remove_worktree") as remove:
                _gc_apply.apply_removals(report, revalidate=lambda: report, run_git=_forbidden_git)
        assert [c.args[0] for c in remove.call_args_list] == ["/repo/a"]
        assert report.remove_errors == []

    def test_the_baseline_comes_from_the_decision_not_from_a_second_read(self):
        """Reading the baseline separately lets a commit become its own baseline.

        Every ``_head_of`` call here agrees, so a baseline taken by reading is
        self-consistent and the removal proceeds. Only the recheck decision
        remembers where the worktree was when it was judged safe, and it
        disagrees, which is what has to withhold the removal.
        """
        report = _report(_live("/repo/a"))
        with patch(f"{_MODULE}._gc_apply._head_of", return_value="9" * 40):
            with patch(f"{_MODULE}._gc_apply.remove_worktree") as remove:
                _gc_apply.apply_removals(report, revalidate=lambda: report, run_git=_forbidden_git)
        remove.assert_not_called()
        assert any("HEAD moved" in e for e in report.remove_errors)

    def test_each_candidate_is_re_read_on_its_own_turn_not_once_up_front(self):
        """A single up-front snapshot is exactly the staleness this guard exists to fix."""
        report = _report(_live("/repo/a"), _live("/repo/b"))
        with patch(f"{_MODULE}._gc_apply._head_of", return_value=_STUB_HEAD) as head:
            with patch(f"{_MODULE}._gc_apply.remove_worktree"):
                _gc_apply.apply_removals(report, revalidate=lambda: report, run_git=_forbidden_git)
        reads = [c.args[0] for c in head.call_args_list]
        assert reads == ["/repo/a", "/repo/b"], "one read each, taken on that candidate's turn"

    def test_a_reflog_that_became_the_only_anchor_withholds_that_removal(self):
        """The case no comparison of HEAD against HEAD can see.

        A worktree that commits and resets ends where it started, so the HEAD
        check passes and the commit survives with nothing but this entry's
        reflog naming it. Proved against real git in
        ``test_gc_worktrees_real_git_apply.py``.
        """
        report = _report(_live("/repo/a"), _live("/repo/b"))
        stranded = {
            "/repo/a": "",
            "/repo/b": "WARNING: its admin directory is the only anchor for 1",
        }

        with patch(
            f"{_MODULE}._gc_reasons.reflog_only_work", side_effect=lambda p, _m, _g: stranded[p]
        ):
            with patch(f"{_MODULE}._gc_apply.remove_worktree") as remove:
                _gc_apply.apply_removals(report, revalidate=lambda: report, run_git=_forbidden_git)
        assert [c.args[0] for c in remove.call_args_list] == ["/repo/a"]
        assert any("/repo/b" in e and "only anchor" in e for e in report.remove_errors)


class TestRevalidation:
    """A plan is a snapshot. Apply must re-answer the safety questions.

    Verified against real git: a detached worktree that is clean and reachable
    when the plan is built, then takes a commit before apply runs, is still
    accepted by ``git worktree remove`` and its new commit becomes unreachable.
    """

    def test_a_candidate_that_stopped_qualifying_is_not_removed(self):
        report = _report(_live("/repo/a"), _live("/repo/b"))
        moved_on = _report(
            _live("/repo/a"),
            Decision("/repo/b", None, remove=False, reason="detached HEAD (no branch to evaluate)"),
        )
        with patch(f"{_MODULE}._gc_apply.remove_worktree") as remove:
            _gc_apply.apply_removals(report, revalidate=lambda: moved_on, run_git=_forbidden_git)
        assert [c.args[0] for c in remove.call_args_list] == ["/repo/a"]
        assert report.removed == ["/repo/a"]

    def test_the_skip_records_what_changed_not_merely_that_something_did(self):
        report = _report(_live("/repo/b"))
        moved_on = _report(Decision("/repo/b", None, remove=False, reason="uncommitted changes"))
        _gc_apply.apply_removals(report, revalidate=lambda: moved_on, run_git=_forbidden_git)
        assert any("/repo/b" in e and "uncommitted changes" in e for e in report.remove_errors), (
            report.remove_errors
        )

    def test_a_candidate_that_vanished_entirely_is_skipped(self):
        report = _report(_live("/repo/a"))
        with patch(f"{_MODULE}._gc_apply.remove_worktree") as remove:
            _gc_apply.apply_removals(report, revalidate=lambda: _report(), run_git=_forbidden_git)
        remove.assert_not_called()
        assert any("no longer registered" in e for e in report.remove_errors)

    def test_a_path_the_recheck_newly_proposes_is_not_removed(self):
        """The reviewed plan bounds the blast radius; the recheck only narrows it."""
        report = _report(_live("/repo/a"))
        wider = _report(_live("/repo/a"), _live("/repo/surprise"))
        with patch(f"{_MODULE}._gc_apply.remove_worktree") as remove:
            _gc_apply.apply_removals(report, revalidate=lambda: wider, run_git=_forbidden_git)
        assert [c.args[0] for c in remove.call_args_list] == ["/repo/a"]

    def test_a_partial_recheck_blocks_the_whole_apply(self):
        report = _report(_live("/repo/a"))
        partial = _report(_live("/repo/a"), Decision("/repo/z", None, False, KEEP_TIME_BUDGET))
        with patch(f"{_MODULE}._gc_apply.remove_worktree") as remove:
            _gc_apply.apply_removals(report, revalidate=lambda: partial, run_git=_forbidden_git)
        remove.assert_not_called()
        assert any("recheck" in e and "refused" in e for e in report.remove_errors)

    def test_a_recheck_without_proc_blocks_the_whole_apply(self):
        report = _report(_live("/repo/a"))
        blind = _report(_live("/repo/a"))
        blind.occupancy_unavailable = True
        with patch(f"{_MODULE}._gc_apply.remove_worktree") as remove:
            _gc_apply.apply_removals(report, revalidate=lambda: blind, run_git=_forbidden_git)
        remove.assert_not_called()
        assert any("recheck" in e and "/proc" in e for e in report.remove_errors)

    def test_an_empty_plan_costs_no_recheck(self):
        report = _report(_keep_stale("/gone/a"))

        def explode():
            raise AssertionError("rechecked a plan with nothing to remove")

        _gc_apply.apply_removals(report, revalidate=explode, run_git=_forbidden_git)
        assert report.removed == []


class TestApply:
    """Removal is per path, and it stops at the first thing it cannot explain."""

    def test_a_candidate_goes_through_remove_worktree(self):
        report = _report(_live("/repo/a"))
        with patch(f"{_MODULE}._gc_apply.remove_worktree") as remove:
            _gc_apply.apply_removals(report, revalidate=_agrees(report), run_git=_forbidden_git)
        assert [c.args[0] for c in remove.call_args_list] == ["/repo/a"]
        assert report.removed == ["/repo/a"]

    def test_a_kept_entry_is_never_touched(self):
        report = _report(_live("/repo/a"), _keep_unreachable("/gone/b"), _keep_stale("/gone/c"))
        with patch(f"{_MODULE}._gc_apply.remove_worktree") as remove:
            _gc_apply.apply_removals(report, revalidate=_agrees(report), run_git=_forbidden_git)
        assert [c.args[0] for c in remove.call_args_list] == ["/repo/a"]
        assert report.removed == ["/repo/a"]

    def test_one_kept_entry_does_not_block_the_candidates(self):
        report = _report(
            _keep_unreachable("/gone/x"),
            *(_live(f"/repo/{i}") for i in range(5)),
        )
        with patch(f"{_MODULE}._gc_apply.remove_worktree"):
            _gc_apply.apply_removals(report, revalidate=_agrees(report), run_git=_forbidden_git)
        assert report.removed == [f"/repo/{i}" for i in range(5)]

    def test_a_failed_removal_stops_the_batch(self):
        """``git worktree remove`` is not atomic: a failure can still have deleted
        the directory. One unexplained state must not become several."""
        report = _report(_live("/repo/a"), _live("/repo/b"), _live("/repo/c"))

        def fail_on_a(path: str, _run: object) -> None:
            if path == "/repo/a":
                raise RuntimeError("still locked")

        with patch(f"{_MODULE}._gc_apply.remove_worktree", side_effect=fail_on_a) as remove:
            _gc_apply.apply_removals(report, revalidate=_agrees(report), run_git=_forbidden_git)
        assert [c.args[0] for c in remove.call_args_list] == ["/repo/a"]
        assert report.removed == []
        assert any("/repo/a" in e and "still locked" in e for e in report.remove_errors)

    def test_the_failure_says_the_path_may_be_half_removed(self):
        report = _report(_live("/repo/a"), _live("/repo/b"))
        with patch(f"{_MODULE}._gc_apply.remove_worktree", side_effect=RuntimeError("denied")):
            _gc_apply.apply_removals(report, revalidate=_agrees(report), run_git=_forbidden_git)
        joined = " ".join(report.remove_errors)
        assert "half-removed" in joined
        assert "1 candidate" in joined

    def test_removals_before_the_failure_are_still_recorded(self):
        report = _report(_live("/repo/a"), _live("/repo/b"))

        def fail_on_b(path: str, _run: object) -> None:
            if path == "/repo/b":
                raise RuntimeError("denied")

        with patch(f"{_MODULE}._gc_apply.remove_worktree", side_effect=fail_on_b):
            _gc_apply.apply_removals(report, revalidate=_agrees(report), run_git=_forbidden_git)
        assert report.removed == ["/repo/a"]


class TestPlanMatchesApply:
    """The contract the old code broke: the plan must predict what apply does."""

    def test_apply_removes_exactly_the_paths_the_plan_named(self):
        report = _report(
            _live("/repo/a"),
            _live("/repo/b"),
            _keep_unreachable("/gone/c"),
            Decision("/repo/d", "feat/d", remove=False, reason="uncommitted changes"),
        )
        planned = [d.path for d in report.candidates]
        with patch(f"{_MODULE}._gc_apply.remove_worktree"):
            _gc_apply.apply_removals(report, revalidate=_agrees(report), run_git=_forbidden_git)
        assert report.removed == planned

    def test_a_kept_stale_entry_is_not_listed_as_a_candidate(self):
        report = _report(_keep_unreachable("/gone/b"), _keep_stale("/gone/c"))
        assert report.candidates == []
        assert [d.path for d in report.kept] == ["/gone/b", "/gone/c"]
