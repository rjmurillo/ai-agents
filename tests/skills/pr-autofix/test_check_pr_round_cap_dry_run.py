"""Tests for check_pr_round_cap.py --dry-run and its environment-default errors."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from round_cap_harness import MainHarness, _mod

main = _mod.main
build_parser = _mod.build_parser
render_state_marker = _mod.render_state_marker


class TestDryRun(MainHarness):
    def _run(self, comments, argv, capsys):
        patches = self._patch_common(list_comments_result=comments)
        with (
            patches[0],
            patches[1],
            patches[2],
            patch("check_pr_round_cap._post_comment") as post_mock,
        ):
            rc = main(["--pull-request", "7", "--output-format", "json", *argv])
        return rc, json.loads(capsys.readouterr().out), post_mock

    def test_first_round_reports_act_and_posts_no_state_marker(self, capsys):
        rc, out, post_mock = self._run([], ["--dry-run"], capsys)

        assert rc == 0
        assert out["Data"]["action"] == "ACT"
        assert out["Data"]["dryRun"] is True
        assert out["Data"]["escalation_posted"] is False
        post_mock.assert_not_called()

    def test_escalation_keeps_exit_code_one_and_posts_no_note(self, capsys):
        now = datetime.now(UTC)
        prior = render_state_marker(
            {"round": 4, "first_seen": now.isoformat(), "last_round_at": now.isoformat()},
        )

        rc, out, post_mock = self._run([{"body": prior}], ["--dry-run"], capsys)

        assert rc == 1
        assert out["Data"]["action"] == "ESCALATE"
        assert out["Data"]["escalation_posted"] is False
        post_mock.assert_not_called()

    def test_default_run_has_no_dry_run_key_and_posts_the_marker(self, capsys):
        rc, out, post_mock = self._run([], [], capsys)

        assert rc == 0
        assert "dryRun" not in out["Data"]
        assert post_mock.call_count == 1


class TestEnvironmentDefaults:
    @pytest.mark.parametrize(
        ("name", "value"),
        [("PR_AUTOFIX_MAX_ROUNDS", "five"), ("PR_AUTOFIX_MAX_ROUND_HOURS", "4h")],
    )
    def test_malformed_value_exits_2_naming_the_variable(self, monkeypatch, capsys, name, value):
        monkeypatch.setenv(name, value)

        with pytest.raises(SystemExit) as exc:
            build_parser()

        err = capsys.readouterr().err
        assert exc.value.code == 2
        assert name in err
        assert "Expected a number" in err

    def test_valid_values_still_parse(self, monkeypatch):
        monkeypatch.setenv("PR_AUTOFIX_MAX_ROUNDS", "9")
        monkeypatch.setenv("PR_AUTOFIX_MAX_ROUND_HOURS", "2.5")

        args = build_parser().parse_args(["--pull-request", "1"])

        assert args.max_rounds == 9
        assert args.max_hours == 2.5
