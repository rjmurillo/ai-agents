"""Stale admin entries in worktree GC: what ``decide`` reports about them.

A worktree whose directory is gone leaves an admin entry behind. Every git
command run inside that directory fails, so the tool used to classify all 62
of them on this machine as "git inspection failed" and report KEEP, while
``--apply`` pruned them anyway. The dry-run plan contradicted what apply did.

These tests pin what the plan says: that a stale entry is recognised whether
or not git set ``prunable``, that a stale entry whose HEAD no ref contains is
kept rather than pruned, and that every independent loss channel is named,
because rescuing the HEAD rescues neither the index nor the reflog.

The probes that answer those questions live in ``_gc_stale.py`` and are tested
in ``test_gc_stale_probes.py``. What ``--apply`` then does with the plan is
tested in ``test_gc_worktrees_stale_apply.py``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.maintenance import _gc_parse, _gc_reasons, _gc_stale, worktree_report
from scripts.maintenance.gc_worktrees import (
    KEEP_LOCKED,
    KEEP_MAIN,
    KEEP_TIME_BUDGET,
    Decision,
    Worktree,
    decide,
)
from scripts.maintenance.worktree_report import KEEP_STALE, KEEP_STALE_UNREACHABLE

_MAIN = "/repo/main"
_BASE = "origin/main"
_SHA = "f30c6952bf2da328bcff0aecc74ff05de3558df7"

_MODULE = "scripts.maintenance.gc_worktrees"


_STUB_HEAD = "f" * 40


@pytest.fixture(autouse=True)
def _stub_pre_removal_head():
    """Unit tests name paths that do not exist, so the pre-removal HEAD read is stubbed.

    ``apply_removals`` reads each candidate's HEAD twice, once with the recheck
    and once immediately before removing it, and refuses when the two differ.
    Against a fabricated path both reads fail and every removal is withheld,
    which would hide what these tests are actually about. Tests that care about
    the comparison patch it again with their own values.
    """
    with patch(f"{_MODULE}._gc_apply._head_of", return_value=_STUB_HEAD):
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

    def test_a_stale_entry_is_kept_even_when_its_head_is_reachable(self):
        """``prunable`` cannot separate a deleted worktree from a moved one.

        A worktree that was moved rather than deleted carries the same marker
        and is still in use, so removing its admin record breaks a live
        checkout. Reachable HEAD is necessary but nowhere near sufficient.
        """
        decision = _decide(_stale(), reachable=True)
        assert decision.remove is False
        assert decision.reason == KEEP_STALE

    def test_the_kept_reason_names_the_guarded_manual_command(self):
        """A reason that only says no is not actionable."""
        decision = _decide(_stale(), reachable=True)
        assert "git worktree repair" in decision.reason
        assert "git worktree remove" in decision.reason

    def test_the_kept_reason_never_recommends_a_blanket_prune(self):
        """``prune`` takes no path, so clearing one entry would clear unsafe siblings."""
        decision = _decide(_stale(), reachable=True)
        assert "prune" not in decision.reason

    def test_repair_is_offered_before_removal(self):
        """A moved worktree is the recoverable case, so it must be read first."""
        reason = _decide(_stale(), reachable=True).reason
        assert reason.index("repair") < reason.index("remove")

    def test_a_stale_entry_whose_head_is_unreachable_says_so_specifically(self):
        """Unreachable is the louder warning and must not collapse into the generic one."""
        decision = _decide(_stale(), reachable=False)
        assert decision.remove is False
        assert KEEP_STALE_UNREACHABLE in decision.reason
        assert decision.reason.startswith("WARNING")
        assert decision.reason != KEEP_STALE

    def test_the_kept_reason_carries_the_sha_needed_to_rescue_it(self):
        """A path alone is not actionable; the rescue command needs the SHA."""
        decision = _decide(_stale(), reachable=False)
        assert f"git branch gc-rescue-{_SHA} {_SHA}" in decision.reason

    def test_a_missing_head_never_renders_as_a_literal_none(self):
        """``git branch <name> None`` is a command that cannot work and looks like one that can."""
        decision = _decide(_stale(head=None), reachable=False)
        assert "None" not in decision.reason
        assert "recorded HEAD is missing" in decision.reason

    def test_a_stale_entry_past_the_time_budget_costs_no_reachability_call(self):
        """The budget guard must precede the subprocess the check spawns."""
        with patch(f"{_MODULE}._gc_reasons.stale_head_is_reachable") as reachable:
            decision = decide(_stale(), _MAIN, _BASE, cwds=frozenset(), inspect=False)
        reachable.assert_not_called()
        assert decision.reason == KEEP_TIME_BUDGET
        assert decision.remove is False

    def test_no_git_command_runs_inside_the_missing_worktree(self):
        """The old code ran git in a directory that no longer exists.

        The diagnostics do call git, but every call must run in the main
        worktree. A call whose ``cwd`` is the vanished path is the regression
        this test exists to catch.
        """
        seen: list[str | None] = []

        def record(_args, cwd=None):
            seen.append(cwd)
            return ""

        with patch(f"{_MODULE}._run_git", side_effect=record):
            _decide(_stale(path="/gone/wt"), reachable=True)
        assert "/gone/wt" not in seen, seen
        assert not any(c and c.startswith("/gone") for c in seen), seen

    def test_no_stale_entry_is_ever_a_removal_candidate(self):
        """The blanket guarantee, independent of any single reason string."""
        for reachable in (True, False):
            for worktree in (_stale(), _stale(branch="feat/x", detached=False)):
                decision = _decide(worktree, reachable=reachable)
                assert decision.remove is False, (reachable, worktree)

    def test_a_locked_stale_entry_stays_locked(self):
        decision = _decide(_stale(locked=True), reachable=True)
        assert decision.reason.startswith(KEEP_LOCKED)

    def test_a_locked_stale_entry_still_discloses_what_clearing_it_would_destroy(self):
        """A lock is temporary. The index and reflog risk outlives it."""
        decision = _decide(_stale(locked=True), reachable=False, staged="staged")
        assert KEEP_LOCKED in decision.reason
        assert "its index holds staged work" in decision.reason
        assert KEEP_STALE_UNREACHABLE in decision.reason

    def test_a_locked_healthy_worktree_carries_no_stale_diagnostics(self):
        """Negative control: only ``prunable`` entries have an orphaned admin dir."""
        decision = _decide(_stale(prunable="", locked=True), reachable=True, present=True)
        assert decision.reason == KEEP_LOCKED

    def test_the_main_worktree_wins_even_if_git_calls_it_prunable(self):
        decision = _decide(_stale(path=_MAIN), reachable=True)
        assert decision.reason == KEEP_MAIN

    def test_a_stale_entry_on_a_branch_keeps_its_branch_in_the_decision(self):
        decision = _decide(_stale(branch="feat/x", detached=False), reachable=True)
        assert decision.branch == "feat/x"


class TestReachability:
    """The guard fails safe: anything it cannot confirm counts as unreachable.

    ``run_git`` is a parameter, so these pass a stub instead of patching a
    module global. The stub is the whole dependency, which is what makes the
    fail-safe cases below cheap to state.
    """

    def test_a_head_contained_by_a_ref_is_reachable(self):
        assert _gc_reasons.stale_head_is_reachable(_SHA, lambda _: "refs/heads/main\n") is True

    def test_a_head_no_ref_contains_is_unreachable(self):
        assert _gc_reasons.stale_head_is_reachable(_SHA, lambda _: "\n") is False

    def test_a_git_failure_is_unknown_not_unreachable(self):
        """Both keep the worktree; only one of them is a fact.

        "No ref contains its HEAD" is a measurement. When the subprocess
        raised, nobody took it.
        """

        def boom(_):
            raise RuntimeError("boom")

        assert _gc_reasons.stale_head_is_reachable(_SHA, boom) is None

    def test_the_warning_says_unknown_rather_than_unreachable_after_a_failure(self):
        """The three-valued answer has to reach the sentence the reader sees."""

        def boom(_):
            raise RuntimeError("boom")

        unknown = _gc_reasons._head_warning(_SHA, boom)
        measured = _gc_reasons._head_warning(_SHA, lambda _: "\n")
        assert worktree_report.KEEP_STALE_HEAD_UNKNOWN in unknown, unknown
        assert worktree_report.KEEP_STALE_UNREACHABLE in measured, measured
        assert worktree_report.KEEP_STALE_UNREACHABLE not in unknown, unknown
        for warning in (unknown, measured):
            assert f"git branch gc-rescue-{_SHA} {_SHA}" in warning, warning

    def test_a_missing_head_counts_as_unreachable(self):
        assert _gc_reasons.stale_head_is_reachable(None, lambda _: "") is False
        assert _gc_reasons.stale_head_is_reachable("", lambda _: "") is False

    def test_a_missing_head_costs_no_git_call(self):
        calls = []
        _gc_reasons.stale_head_is_reachable(None, lambda a: calls.append(a) or "")
        assert calls == []


class TestStagedContentWarning:
    """The report tells operators to run prune, so it must check what prune destroys.

    Verified against real git: ``git worktree prune`` deletes the admin
    directory including the orphaned index, and a blob that was ``git add``ed
    but never committed has no other anchor. Recommending prune without
    checking would hand the operator a silent data-loss path.
    """

    def test_a_clean_index_gets_the_plain_reason(self):
        decision = _decide(_stale(), staged="clean")
        assert decision.reason == KEEP_STALE

    def test_staged_content_warns_and_names_the_recovery_command(self):
        decision = _decide(_stale(), staged="staged", admin="/repo/.git/worktrees/wt")
        assert "WARNING" in decision.reason
        assert "GIT_INDEX_FILE=/repo/.git/worktrees/wt/index" in decision.reason
        assert "git checkout-index" in decision.reason

    def test_an_unreadable_index_discloses_the_gap_instead_of_claiming_either(self):
        """A git failure must not read as 'staged work' or as 'nothing there'."""
        decision = _decide(_stale(), staged="unknown")
        assert "cannot be ruled out" in decision.reason
        assert "WARNING" not in decision.reason

    def test_an_unlocatable_admin_entry_says_so(self):
        decision = _decide(_stale(), admin=None)
        assert "could not locate its admin entry" in decision.reason

    def test_the_warning_is_read_before_the_command(self):
        """The reason ends with a runnable command; a skimmer must hit the warning first."""
        reason = _decide(_stale(), staged="staged").reason
        assert reason.index("WARNING") < reason.index("git worktree remove")

    def test_a_clean_entry_carries_no_warning_at_all(self):
        """Warning on every entry is the same as warning on none."""
        assert _decide(_stale(), staged="clean").reason == KEEP_STALE

    def test_an_unreachable_head_never_suppresses_the_staged_warning(self):
        """Rescuing HEAD rescues nothing in the index; both losses need their own command.

        This inverts an earlier assertion that treated the unreachable HEAD as
        outranking the staged index. Verified against real git: one entry can
        carry an unreachable HEAD, staged blobs, and reflog-only commits at the
        same time, and ``git branch`` recovers only the first. A reader who
        followed the old single-reason output lost the other two.
        """
        decision = _decide(_stale(), reachable=False, staged="staged")
        assert KEEP_STALE_UNREACHABLE in decision.reason
        assert "its index holds staged work" in decision.reason

    def test_the_head_rescue_is_read_before_the_index_rescue(self):
        """Both appear; the committed work is still the first thing to save."""
        reason = _decide(_stale(), reachable=False, staged="staged").reason
        assert reason.index(KEEP_STALE_UNREACHABLE) < reason.index("its index holds staged work")

    def test_no_warning_ends_in_a_period_that_would_corrupt_its_command(self):
        """``git branch gc-rescue-x <sha>.`` fails with ``bad object``."""
        reason = _decide(_stale(), reachable=False, staged="staged").reason
        assert f"{_SHA}." not in reason
        assert "--prefix=<somewhere>/." not in reason


class TestReflogWarning:
    """The admin reflog is the only anchor for a detached worktree's abandoned commits."""

    @staticmethod
    def _reason(orphans, staged: str = "clean") -> str:
        with patch(
            f"{_MODULE}._gc_reasons._gc_stale.unreachable_reflog_commits", return_value=orphans
        ):
            return _decide(_stale(), staged=staged).reason

    def test_an_abandoned_commit_is_named_with_a_rescue_command(self):
        sha = "a" * 40
        reason = self._reason([sha])
        assert "WARNING" in reason
        assert f"git branch gc-rescue-{sha} {sha}" in reason

    def test_no_orphans_means_no_warning(self):
        assert self._reason([]) == KEEP_STALE

    def test_an_unreadable_reflog_discloses_the_gap_instead_of_claiming_either(self):
        reason = self._reason(None)
        assert "WARNING" not in reason
        assert "could not be read" in reason

    def test_only_three_rescue_commands_are_printed_and_the_rest_are_counted(self):
        reason = self._reason([f"{i:040x}" for i in range(7)])
        assert reason.count("git branch gc-rescue-") == 3
        assert "and 4 more" in reason

    def test_both_warnings_appear_when_index_and_reflog_are_both_at_risk(self):
        reason = self._reason(["b" * 40], staged="staged")
        assert "its index holds staged work" in reason
        assert "its reflog is the only anchor" in reason
        assert reason.index("WARNING") < reason.index("git worktree remove")


class TestCheckoutPresence:
    """A pathname is not an identity.

    ``decide`` treats a missing checkout as a stale entry. Asking whether the
    *directory* is there answers a weaker question than the one that matters:
    delete a worktree and put an ordinary directory at the same path and the
    entry reads as healthy while its admin record points at something that is
    no longer that worktree. The ``.git`` marker is what makes it that
    worktree, so that is what gets asked.
    """

    def test_a_linked_checkout_carries_the_marker(self, tmp_path):
        checkout = tmp_path / "wt"
        checkout.mkdir()
        (checkout / ".git").write_text("gitdir: /repo/.git/worktrees/wt\n", encoding="utf-8")
        assert _gc_stale.linked_checkout_present(str(checkout)) is True

    def test_a_replacement_directory_does_not(self, tmp_path):
        """The case a bare ``exists`` call cannot see."""
        replacement = tmp_path / "wt"
        replacement.mkdir()
        assert Path(replacement).exists() is True
        assert _gc_stale.linked_checkout_present(str(replacement)) is False

    def test_an_absent_path_is_absent(self, tmp_path):
        assert _gc_stale.linked_checkout_present(str(tmp_path / "gone")) is False
