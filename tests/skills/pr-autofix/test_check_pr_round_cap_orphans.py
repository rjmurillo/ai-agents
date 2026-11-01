"""check_pr_round_cap.py reports unpushed local commits when escalated (issue #5447).

The scan is read-only: it adds an ``orphaned_commits`` object to the envelope
and a warning to the human summary, and never changes the exit code. The git
logic has its own tests in test_orphaned_commits.py; these cover the wiring.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from round_cap_harness import MainHarness, _mod

main = _mod.main
render_state_marker = _mod.render_state_marker

AHEAD = {
    "status": "ahead",
    "live_head": "sha-1",
    "commits": [{"sha": "b" * 40, "subject": "drop duplicate gate", "risks": []}],
    "warning": "1 local commit(s) ahead of live PR head sha-1. Treat as unverified.",
}
ARGS = ["--pull-request", "7", "--max-rounds", "5", "--max-hours", "4"]


def _state(**extra):
    now = datetime.now(UTC)
    base = {"round": 1, "first_seen": now.isoformat(), "last_round_at": now.isoformat()}
    return render_state_marker({**base, **extra})


class TestOrphanedCommitsWiring(MainHarness):
    def _run(self, patches, extra_args=("--output-format", "json"), scan=None):
        scan_patch = patch("check_pr_round_cap.scan_if_escalated", return_value=scan, wraps=None)
        with patches[0], patches[1], patches[2], patch("check_pr_round_cap._post_comment"):
            if scan is None:
                return main([*ARGS, *extra_args]), None
            with scan_patch as spy:
                return main([*ARGS, *extra_args]), spy

    def test_first_round_act_is_not_checked_and_runs_no_git(self, capsys):
        patches = self._patch_common()
        with patch("github_core.orphaned_commits.subprocess.run") as git:
            rc, _ = self._run(patches)
        assert rc == 0
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["orphaned_commits"]["status"] == "not_checked"
        assert data["orphaned_warning"] == ""
        git.assert_not_called()

    def test_escalating_call_scans_with_live_head(self, capsys):
        patches = self._patch_common(list_comments_result=[{"body": _state(round=4)}])
        rc, spy = self._run(patches, scan=AHEAD)
        assert rc == 1
        spy.assert_called_once_with(True, "sha-1", pr_checkout=False)
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["action"] == "ESCALATE"
        assert data["orphaned_commits"] == AHEAD
        assert data["orphaned_warning"] == AHEAD["warning"]

    def test_escalated_prior_state_scans_even_after_a_reset_acts(self, capsys):
        old = datetime.now(UTC) - timedelta(hours=10)
        prior = render_state_marker(
            {
                "round": 2,
                "first_seen": old.isoformat(),
                "last_round_at": old.isoformat(),
                "head_sha": "old-sha",
                "escalated": True,
            }
        )
        patches = self._patch_common(list_comments_result=[{"body": prior}], head_sha="sha-1")
        rc, spy = self._run(patches, scan=AHEAD)
        assert rc == 0
        spy.assert_called_once_with(True, "sha-1", pr_checkout=False)
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["action"] == "ACT"
        assert data["orphaned_commits"]["status"] == "ahead"

    def test_worktree_flag_scans_through_that_worktree(self, capsys):
        patches = self._patch_common(list_comments_result=[{"body": _state(round=4)}])
        with patch("check_pr_round_cap.worktree_runner", return_value="RUNNER") as make:
            rc, spy = self._run(
                patches,
                extra_args=("--output-format", "json", "--worktree", "/wt/pr-7"),
                scan=AHEAD,
            )
        assert rc == 1
        make.assert_called_once_with("/wt/pr-7")
        spy.assert_called_once_with(True, "sha-1", "RUNNER", pr_checkout=True)

    def test_no_worktree_flag_scans_the_current_directory(self):
        patches = self._patch_common(list_comments_result=[{"body": _state(round=4)}])
        with patch("check_pr_round_cap.worktree_runner") as make:
            _, spy = self._run(patches, scan=AHEAD)
        make.assert_not_called()
        spy.assert_called_once_with(True, "sha-1", pr_checkout=False)

    def test_unescalated_prior_state_does_not_scan(self):
        patches = self._patch_common(list_comments_result=[{"body": _state()}])
        rc, spy = self._run(patches, scan=AHEAD)
        assert rc == 0
        spy.assert_called_once_with(False, "sha-1", pr_checkout=False)

    def test_missing_live_head_on_escalation_is_unverified(self, capsys):
        patches = self._patch_common(
            list_comments_result=[{"body": _state(round=4)}], head_sha=None
        )
        rc, _ = self._run(patches)
        assert rc == 1
        data = json.loads(capsys.readouterr().out)["Data"]
        assert data["orphaned_commits"]["status"] == "unverified"

    def test_human_summary_carries_the_warning(self, capsys):
        patches = self._patch_common(list_comments_result=[{"body": _state(round=4)}])
        rc, _ = self._run(patches, extra_args=("--output-format", "human"), scan=AHEAD)
        assert rc == 1
        assert "Treat as unverified" in capsys.readouterr().out

    def test_human_summary_without_warning_is_unchanged(self, capsys):
        patches = self._patch_common()
        rc, _ = self._run(patches, extra_args=("--output-format", "human"))
        assert rc == 0
        assert "unverified" not in capsys.readouterr().out

    def test_warning_is_logged_without_the_commit_text(self, caplog):
        patches = self._patch_common(list_comments_result=[{"body": _state(round=4)}])
        with caplog.at_level("WARNING"):
            self._run(patches, scan=AHEAD)
        messages = [r.getMessage() for r in caplog.records]
        assert any("op=round_cap_orphaned_commits pr=7 status=ahead" in m for m in messages)
        assert not any("drop duplicate gate" in m for m in messages)
