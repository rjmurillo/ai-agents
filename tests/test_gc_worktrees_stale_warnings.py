"""What the stale-entry reason warns about, and in what order.

A stale admin entry can hold three independent losses at once: a HEAD no ref
contains, blobs staged into the orphaned index, and commits anchored only by the
admin directory. Each needs its own rescue command, because recovering one
recovers neither of the others. These tests pin that every live loss is named,
that a clean entry is named as clean, and that a reader who skims hits the
warning before the command that destroys the thing it warns about.

The probes that answer those questions are tested in ``test_gc_stale_probes.py``.
What ``decide`` reports about a stale entry is tested in
``test_gc_worktrees_stale.py``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts.maintenance.worktree_report import KEEP_STALE, KEEP_STALE_UNREACHABLE
from tests.gc_stale_unit import (
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
            f"{MODULE}._gc_reasons._gc_stale.unreachable_reflog_commits", return_value=orphans
        ):
            return decide_stale(stale_worktree(), staged=staged).reason

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
