"""Tests for update_pr_branch.py --wait: success, timeout, and poll budget.

AC numbers refer to the acceptance criteria in the PR body.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from tests.update_pr_branch_harness import (
    NEW_HEAD,
    OLD_HEAD,
    FakeClock,
    FakeGh,
    envelope,
    pr_json,
    run_main,
    script,
)


class TestWait:
    def test_wait_reports_new_head(self, capsys):
        """AC7: poll until compare shows the new head is not behind, then report it."""
        clock = FakeClock()
        fake = FakeGh(
            pr_views=[pr_json(), pr_json(), pr_json(head=NEW_HEAD)],
            behind=["2", "2", "0"],
        )
        with patch.object(script, "_monotonic", clock.monotonic), patch.object(
            script, "_sleep", clock.sleep,
        ):
            rc = run_main(["--pull-request", "50", "--wait", "--timeout-seconds", "60"], fake)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["action"] == "updated"
        assert env["Data"]["old_head_sha"] == OLD_HEAD
        assert env["Data"]["new_head_sha"] == NEW_HEAD
        assert env["Data"]["wait_result"] == "head_changed"
        assert clock.sleeps, "expected at least one poll interval"

    def test_wait_ignores_head_change_while_still_behind(self, capsys):
        """AC8: an unrelated push moves the head but the PR stays behind; that is
        not success, so the bounded wait times out."""
        clock = FakeClock()
        fake = FakeGh(pr_views=[pr_json(), pr_json(head=NEW_HEAD)], behind=["2"])
        with patch.object(script, "_monotonic", clock.monotonic), patch.object(
            script, "_sleep", clock.sleep,
        ):
            rc = run_main(["--pull-request", "50", "--wait", "--timeout-seconds", "12"], fake)
        env = envelope(capsys)
        assert rc == 3
        assert env["Data"]["last_head_sha"] == NEW_HEAD

    def test_wait_with_unreadable_compare_times_out_not_succeeds(self, capsys):
        """AC8: compare fails mid-wait; a head change is unverifiable, so the wait
        fails closed to the timeout and names the precheck failure."""
        clock = FakeClock()
        fake = FakeGh(
            pr_views=[pr_json(), pr_json(head=NEW_HEAD)],
            behind=["2", "2", "garbage"],
        )
        with patch.object(script, "_monotonic", clock.monotonic), patch.object(
            script, "_sleep", clock.sleep,
        ):
            rc = run_main(["--pull-request", "50", "--wait", "--timeout-seconds", "12"], fake)
        env = envelope(capsys)
        assert rc == 3
        assert env["Data"]["last_head_sha"] == NEW_HEAD
        assert env["Data"]["last_precheck"].startswith("unavailable")

    def test_wait_stops_when_no_longer_behind(self, capsys):
        """AC7: compare reaching 0 also ends the wait."""
        clock = FakeClock()
        fake = FakeGh(behind=["2", "2", "0"])
        with patch.object(script, "_monotonic", clock.monotonic), patch.object(
            script, "_sleep", clock.sleep,
        ):
            rc = run_main(["--pull-request", "50", "--wait", "--timeout-seconds", "60"], fake)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["wait_result"] == "not_behind"

    def test_wait_timeout_exits_3(self, capsys):
        """AC8: the head never moves, so the bounded wait exits 3 Timeout."""
        clock = FakeClock()
        fake = FakeGh(behind=["2"])
        with patch.object(script, "_monotonic", clock.monotonic), patch.object(
            script, "_sleep", clock.sleep,
        ):
            rc = run_main(["--pull-request", "50", "--wait", "--timeout-seconds", "12"], fake)
        env = envelope(capsys)
        assert rc == 3
        assert env["Error"]["Type"] == "Timeout"
        assert env["Data"]["old_head_sha"] == OLD_HEAD
        assert env["Data"]["update_requested"] is True
        assert env["Data"]["last_precheck"] == "ok"
        assert clock.now <= 12


class TestWaitBudget:
    def test_hung_poll_is_capped_by_the_wait_budget_and_exits_3(self, capsys):
        """AC8: a gh call inside --wait gets at most the time left, and a hang
        becomes the wait's own Timeout envelope, not an unbounded stall."""
        fake, limits = FakeGh(), []

        def _hangs_in_wait(cmd, **kwargs):
            if fake.put_calls() and list(cmd[:3]) == ["gh", "pr", "view"]:
                limits.append(kwargs["timeout"])
                raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])
            return fake(cmd, **kwargs)

        clock = FakeClock()
        with patch.object(script, "_monotonic", clock.monotonic), patch.object(
            script, "_sleep", clock.sleep,
        ):
            argv = ["--pull-request", "50", "--wait", "--timeout-seconds", "4"]
            rc = run_main(argv, _hangs_in_wait)
        env = envelope(capsys)
        assert rc == 3
        assert env["Error"]["Type"] == "Timeout"
        assert env["Data"]["update_requested"] is True
        assert "Reading PR state timed out" in env["Data"]["last_precheck"]
        assert limits == [4.0]

    def test_slow_poll_past_the_deadline_times_out_without_sleeping(self, capsys):
        """AC8: a poll that itself runs past the deadline ends the wait at once;
        the loop never sleeps a zero or negative interval."""
        fake, clock = FakeGh(behind=["2"]), FakeClock()

        def _slow_compare(cmd, **kwargs):
            if fake.put_calls() and "/compare/" in " ".join(cmd):
                clock.now += 50
            return fake(cmd, **kwargs)

        with patch.object(script, "_monotonic", clock.monotonic), patch.object(
            script, "_sleep", clock.sleep,
        ):
            argv = ["--pull-request", "50", "--wait", "--timeout-seconds", "30"]
            rc = run_main(argv, _slow_compare)
        env = envelope(capsys)
        assert rc == 3
        assert env["Data"]["last_precheck"] == "ok"
        assert clock.sleeps == []

    def test_wait_help_names_the_real_stop_condition(self):
        """The --wait help matches the loop: compare, not a head change."""
        text = script.build_parser().format_help()
        assert "compare shows the PR is no longer behind" in " ".join(text.split())
