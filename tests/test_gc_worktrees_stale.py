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
in ``test_gc_stale_probes.py``. The warnings the reason carries are tested in
``test_gc_worktrees_stale_warnings.py``. What ``--apply`` then does with the
plan is tested in ``test_gc_worktrees_stale_apply.py``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.maintenance import _gc_parse, _gc_reasons, _gc_stale, worktree_report
from scripts.maintenance.gc_worktrees import (
    KEEP_LOCKED,
    KEEP_MAIN,
    KEEP_TIME_BUDGET,
    Worktree,
    decide,
)
from scripts.maintenance.worktree_report import KEEP_STALE, KEEP_STALE_UNREACHABLE
from tests.gc_stale_unit import (
    BASE,
    MAIN,
    MODULE,
    SHA,
    decide_stale,
    stale_worktree,
    stub_pre_removal_head,
)


@pytest.fixture(autouse=True)
def _stub_pre_removal_head():
    with stub_pre_removal_head():
        yield


def _parse(text: str) -> list[Worktree]:
    """Run the real porcelain parser over canned ``git worktree list`` output."""
    return _gc_parse.list_worktrees(lambda _: text)


class TestPorcelainParsing:
    """``prunable`` is a real porcelain line and must survive the parser."""

    def test_a_prunable_line_with_a_reason_is_captured(self):
        text = (
            f"worktree /gone/wt\nHEAD {SHA}\ndetached\n"
            "prunable gitdir file points to non-existent location\n\n"
        )
        (worktree,) = _parse(text)
        assert worktree.prunable == "gitdir file points to non-existent location"

    def test_a_bare_prunable_line_still_marks_the_entry(self):
        text = f"worktree /gone/wt\nHEAD {SHA}\ndetached\nprunable\n\n"
        (worktree,) = _parse(text)
        assert worktree.prunable == "prunable"

    def test_a_healthy_worktree_has_no_prunable_marker(self):
        text = f"worktree /repo/wt\nHEAD {SHA}\nbranch refs/heads/feat/x\n\n"
        (worktree,) = _parse(text)
        assert worktree.prunable is None

    def test_prunable_does_not_leak_into_the_branch_field(self):
        text = f"worktree /gone/wt\nHEAD {SHA}\ndetached\nprunable whatever\n\n"
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
        decision = decide_stale(stale_worktree(), reachable=True)
        assert decision.remove is False
        assert decision.reason == KEEP_STALE

    def test_the_kept_reason_names_the_guarded_manual_command(self):
        """A reason that only says no is not actionable."""
        decision = decide_stale(stale_worktree(), reachable=True)
        assert "git worktree repair" in decision.reason
        assert "git worktree remove" in decision.reason

    def test_the_kept_reason_never_recommends_a_blanket_prune(self):
        """``prune`` takes no path, so clearing one entry would clear unsafe siblings."""
        decision = decide_stale(stale_worktree(), reachable=True)
        assert "prune" not in decision.reason

    def test_repair_is_offered_before_removal(self):
        """A moved worktree is the recoverable case, so it must be read first."""
        reason = decide_stale(stale_worktree(), reachable=True).reason
        assert reason.index("repair") < reason.index("remove")

    def test_a_stale_entry_whose_head_is_unreachable_says_so_specifically(self):
        """Unreachable is the louder warning and must not collapse into the generic one."""
        decision = decide_stale(stale_worktree(), reachable=False)
        assert decision.remove is False
        assert KEEP_STALE_UNREACHABLE in decision.reason
        assert decision.reason.startswith("WARNING")
        assert decision.reason != KEEP_STALE

    def test_the_kept_reason_carries_the_sha_needed_to_rescue_it(self):
        """A path alone is not actionable; the rescue command needs the SHA."""
        decision = decide_stale(stale_worktree(), reachable=False)
        assert f"git -C {MAIN} branch gc-rescue-{SHA} {SHA}" in decision.reason

    def test_a_missing_head_never_renders_as_a_literal_none(self):
        """``git branch <name> None`` is a command that cannot work and looks like one that can."""
        decision = decide_stale(stale_worktree(head=None), reachable=False)
        assert "None" not in decision.reason
        assert "recorded HEAD is missing" in decision.reason

    def test_a_stale_entry_past_the_time_budget_costs_no_reachability_call(self):
        """The budget guard must precede the subprocess the check spawns."""
        with patch(f"{MODULE}._gc_reasons.stale_head_is_reachable") as reachable:
            decision = decide(stale_worktree(), MAIN, BASE, cwds=frozenset(), inspect=False)
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

        with patch(f"{MODULE}._run_git", side_effect=record):
            decide_stale(stale_worktree(path="/gone/wt"), reachable=True)
        assert "/gone/wt" not in seen, seen
        assert not any(c and c.startswith("/gone") for c in seen), seen

    def test_no_stale_entry_is_ever_a_removal_candidate(self):
        """The blanket guarantee, independent of any single reason string."""
        for reachable in (True, False):
            for worktree in (stale_worktree(), stale_worktree(branch="feat/x", detached=False)):
                decision = decide_stale(worktree, reachable=reachable)
                assert decision.remove is False, (reachable, worktree)

    def test_a_locked_stale_entry_stays_locked(self):
        decision = decide_stale(stale_worktree(locked=True), reachable=True)
        assert decision.reason.startswith(KEEP_LOCKED)

    def test_a_locked_stale_entry_still_discloses_what_clearing_it_would_destroy(self):
        """A lock is temporary. The index and reflog risk outlives it."""
        decision = decide_stale(stale_worktree(locked=True), reachable=False, staged="staged")
        assert KEEP_LOCKED in decision.reason
        assert "its index holds staged work" in decision.reason
        assert KEEP_STALE_UNREACHABLE in decision.reason

    def test_a_locked_healthy_worktree_carries_no_stale_diagnostics(self):
        """Negative control: only ``prunable`` entries have an orphaned admin dir."""
        decision = decide_stale(
            stale_worktree(prunable="", locked=True), reachable=True, present=True
        )
        assert decision.reason == KEEP_LOCKED

    def test_the_main_worktree_wins_even_if_git_calls_it_prunable(self):
        decision = decide_stale(stale_worktree(path=MAIN), reachable=True)
        assert decision.reason == KEEP_MAIN

    def test_a_stale_entry_on_a_branch_keeps_its_branch_in_the_decision(self):
        decision = decide_stale(stale_worktree(branch="feat/x", detached=False), reachable=True)
        assert decision.branch == "feat/x"


class TestReachability:
    """The guard fails safe: anything it cannot confirm counts as unreachable.

    ``run_git`` is a parameter, so these pass a stub instead of patching a
    module global. The stub is the whole dependency, which is what makes the
    fail-safe cases below cheap to state.
    """

    def test_a_head_contained_by_a_ref_is_reachable(self):
        assert _gc_reasons.stale_head_is_reachable(SHA, lambda _: "refs/heads/main\n") is True

    def test_a_head_no_ref_contains_is_unreachable(self):
        assert _gc_reasons.stale_head_is_reachable(SHA, lambda _: "\n") is False

    def test_a_git_failure_is_unknown_not_unreachable(self):
        """Both keep the worktree; only one of them is a fact.

        "No ref contains its HEAD" is a measurement. When the subprocess
        raised, nobody took it.
        """

        def boom(_):
            raise RuntimeError("boom")

        assert _gc_reasons.stale_head_is_reachable(SHA, boom) is None

    def test_the_warning_says_unknown_rather_than_unreachable_after_a_failure(self):
        """The three-valued answer has to reach the sentence the reader sees."""

        def boom(_):
            raise RuntimeError("boom")

        unknown = _gc_reasons._head_warning(SHA, MAIN, boom)
        measured = _gc_reasons._head_warning(SHA, MAIN, lambda _: "\n")
        assert worktree_report.KEEP_STALE_HEAD_UNKNOWN in unknown, unknown
        assert worktree_report.KEEP_STALE_UNREACHABLE in measured, measured
        assert worktree_report.KEEP_STALE_UNREACHABLE not in unknown, unknown
        for warning in (unknown, measured):
            assert f"git -C {MAIN} branch gc-rescue-{SHA} {SHA}" in warning, warning

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
        decision = decide_stale(stale_worktree(), staged="clean")
        assert decision.reason == KEEP_STALE

    def test_staged_content_warns_and_names_the_recovery_command(self):
        decision = decide_stale(stale_worktree(), staged="staged", admin="/repo/.git/worktrees/wt")
        assert "WARNING" in decision.reason
        assert "GIT_INDEX_FILE=/repo/.git/worktrees/wt/index" in decision.reason
        assert "checkout-index" in decision.reason
        # The recovery command and the command that reads the copy back are both
        # ``git -C`` pinned, so a reader who pastes them from outside the
        # repository still reaches the object database that holds the staged
        # blobs rather than failing with "not a git repository".
        assert f"git -C {MAIN} checkout-index" in decision.reason
        assert f"git -C {MAIN} ls-files" in decision.reason

    def test_an_unreadable_index_discloses_the_gap_instead_of_claiming_either(self):
        """A git failure must not read as 'staged work' or as 'nothing there'."""
        decision = decide_stale(stale_worktree(), staged="unknown")
        assert "cannot be ruled out" in decision.reason
        assert "WARNING" not in decision.reason

    def test_an_unlocatable_admin_entry_says_so(self):
        decision = decide_stale(stale_worktree(), admin=None)
        assert "could not locate its admin entry" in decision.reason

    def test_the_warning_is_read_before_the_command(self):
        """The reason ends with a runnable command; a skimmer must hit the warning first."""
        reason = decide_stale(stale_worktree(), staged="staged").reason
        assert reason.index("WARNING") < reason.index("git worktree remove")

    def test_a_clean_entry_carries_no_warning_at_all(self):
        """Warning on every entry is the same as warning on none."""
        assert decide_stale(stale_worktree(), staged="clean").reason == KEEP_STALE

    def test_an_unreachable_head_never_suppresses_the_staged_warning(self):
        """Rescuing HEAD rescues nothing in the index; both losses need their own command.

        This inverts an earlier assertion that treated the unreachable HEAD as
        outranking the staged index. Verified against real git: one entry can
        carry an unreachable HEAD, staged blobs, and reflog-only commits at the
        same time, and ``git branch`` recovers only the first. A reader who
        followed the old single-reason output lost the other two.
        """
        decision = decide_stale(stale_worktree(), reachable=False, staged="staged")
        assert KEEP_STALE_UNREACHABLE in decision.reason
        assert "its index holds staged work" in decision.reason

    def test_the_head_rescue_is_read_before_the_index_rescue(self):
        """Both appear; the committed work is still the first thing to save."""
        reason = decide_stale(stale_worktree(), reachable=False, staged="staged").reason
        assert reason.index(KEEP_STALE_UNREACHABLE) < reason.index("its index holds staged work")

    def test_no_warning_ends_in_a_period_that_would_corrupt_its_command(self):
        """``git branch gc-rescue-x <sha>.`` fails with ``bad object``."""
        reason = decide_stale(stale_worktree(), reachable=False, staged="staged").reason
        assert f"{SHA}." not in reason
        assert "--prefix=<somewhere>/." not in reason


class TestReflogWarning:
    """The admin reflog is the only anchor for a detached worktree's abandoned commits."""

    @staticmethod
    def _reason(orphans, staged: str = "clean") -> str:
        with patch(
            f"{MODULE}._gc_reasons._gc_stale.unreachable_admin_commits", return_value=orphans
        ):
            return decide_stale(stale_worktree(), staged=staged).reason

    def test_an_abandoned_commit_is_named_with_a_rescue_command(self):
        sha = "a" * 40
        reason = self._reason([sha])
        assert "WARNING" in reason
        assert f"git -C {MAIN} branch gc-rescue-{sha} {sha}" in reason

    def test_no_orphans_means_no_warning(self):
        assert self._reason([]) == KEEP_STALE

    def test_an_unreadable_reflog_discloses_the_gap_instead_of_claiming_either(self):
        reason = self._reason(None)
        assert "WARNING" not in reason
        assert "could not be read" in reason

    def test_only_three_rescue_commands_are_printed_and_the_rest_are_counted(self):
        reason = self._reason([f"{i:040x}" for i in range(7)])
        assert reason.count(f"git -C {MAIN} branch gc-rescue-") == 3
        assert "4 more are named under" in reason

    def test_both_warnings_appear_when_index_and_reflog_are_both_at_risk(self):
        reason = self._reason(["b" * 40], staged="staged")
        assert "its index holds staged work" in reason
        assert "its admin directory is the only anchor" in reason
        assert reason.index("WARNING") < reason.index("git worktree remove")


def _linked(root: Path, name: str) -> Path:
    """Stage the file layout git writes for a linked worktree.

    ``<checkout>/.git`` holds ``gitdir: <admin>`` and ``<admin>/gitdir`` holds
    ``<checkout>/.git``. The pair is what identifies the checkout; either half
    alone can be true of a directory that belongs to something else. Verified
    against real git in ``test_gc_worktrees_real_git_stale.py``.
    """
    checkout = root / name
    checkout.mkdir(parents=True)
    admin = root / "main" / ".git" / "worktrees" / name
    admin.mkdir(parents=True)
    (checkout / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    (admin / "gitdir").write_text(f"{checkout / '.git'}\n", encoding="utf-8")
    return checkout


class TestCheckoutPresence:
    """A pathname is not an identity, and neither is a bare marker.

    ``decide`` treats a missing checkout as a stale entry. Asking whether the
    *directory* is there answers a weaker question than the one that matters:
    delete a worktree and put an ordinary directory at the same path and the
    entry reads as healthy while its admin record points at something that is
    no longer that worktree.

    Asking only whether ``.git`` is there is still too weak. Move worktree B
    onto worktree A's deleted path and A's directory holds a marker again, but
    it names B's admin directory. The link has to close: the admin directory
    the marker names must record this same path back.
    """

    def test_a_linked_checkout_carries_the_marker(self, tmp_path):
        checkout = _linked(tmp_path, "wt")
        assert _gc_stale.linked_checkout_present(str(checkout)) is True

    def test_a_marker_naming_another_worktrees_admin_dir_does_not(self, tmp_path):
        """Move worktree B onto worktree A's deleted path.

        A's directory now holds a ``.git`` file, so a marker-exists check calls
        A healthy. The file names B's admin directory, and B's admin directory
        records B's path, so nothing about A's checkout is there. Every probe
        that follows would read B's admin record and report it as A's.
        """
        moved = _linked(tmp_path, "moved")
        vacated = tmp_path / "vacated"
        shutil.move(str(moved), str(vacated))
        assert (vacated / ".git").is_file()
        assert _gc_stale.linked_checkout_present(str(vacated)) is False

    def test_a_marker_naming_a_missing_admin_dir_does_not(self, tmp_path):
        checkout = tmp_path / "wt"
        checkout.mkdir()
        (checkout / ".git").write_text("gitdir: /repo/.git/worktrees/wt\n", encoding="utf-8")
        assert _gc_stale.linked_checkout_present(str(checkout)) is False

    def test_an_empty_marker_does_not(self, tmp_path):
        checkout = tmp_path / "wt"
        checkout.mkdir()
        (checkout / ".git").write_text("gitdir:\n", encoding="utf-8")
        assert _gc_stale.linked_checkout_present(str(checkout)) is False

    def test_a_standalone_repo_replacing_a_linked_path_is_not_the_entry(self, tmp_path):
        """``.git`` is a real directory here, so it is a standalone repository.

        The true main worktree also holds a ``.git`` directory, but it never
        reaches this probe: ``decide`` returns ``KEEP_MAIN`` for it above. So the
        only checkout that arrives here with a ``.git`` directory is a foreign
        standalone repository sitting where a linked worktree used to be, which
        is not this entry and reads as stale. Reading it as present would let
        ``git worktree remove`` delete that unrelated repository.
        """
        foreign = tmp_path / "foreign"
        (foreign / ".git").mkdir(parents=True)
        assert _gc_stale.linked_checkout_present(str(foreign)) is False

    def test_relative_links_resolve_against_the_file_that_holds_them(self, tmp_path):
        """``worktree.useRelativePaths`` writes both sides relative.

        Resolving either against the process working directory instead of
        against its own file turns a healthy worktree into a stale entry.
        """
        checkout = _linked(tmp_path, "wt")
        admin = tmp_path / "main" / ".git" / "worktrees" / "wt"
        (checkout / ".git").write_text(
            f"gitdir: {os.path.relpath(admin, checkout)}\n", encoding="utf-8"
        )
        (admin / "gitdir").write_text(
            f"{os.path.relpath(checkout / '.git', admin)}\n", encoding="utf-8"
        )
        cwd = os.getcwd()
        os.chdir(tmp_path.parent)
        try:
            assert _gc_stale.linked_checkout_present(str(checkout)) is True
        finally:
            os.chdir(cwd)

    def test_a_replacement_directory_does_not(self, tmp_path):
        """The case a bare ``exists`` call cannot see."""
        replacement = tmp_path / "wt"
        replacement.mkdir()
        assert Path(replacement).exists() is True
        assert _gc_stale.linked_checkout_present(str(replacement)) is False

    def test_an_absent_path_is_absent(self, tmp_path):
        assert _gc_stale.linked_checkout_present(str(tmp_path / "gone")) is False
