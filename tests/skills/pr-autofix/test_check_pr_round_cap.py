"""Tests for check_pr_round_cap.py (issue #5056).

pr-autofix's T3/T4 thread-fix loop had no machine-enforced cap on how many
fix/review rounds it runs against one PR. Incidents ran 11-18 rounds over
multi-hour spans before a human intervened (46h wall clock for PR #1887; see
`.project-toolkit/retrospective/2026-05-05-pr-1887-iteration-paradox.md`). This script
is the machine-checked circuit breaker: it records one round per call and
returns ESCALATE when either the round count or the wall-clock budget is
exceeded, mirroring the JSON-envelope contract `check_pr_live_state.py`
already established (issue #2455).

Exit codes follow ADR-035:
    0 - round recorded, under both caps (ACT)
    1 - a cap is exceeded (ESCALATE)
    2 - PR not found (unused by this script; reserved for contract parity)
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package), matching
# tests/test_check_pr_live_state.py's pattern for the sibling gate script.
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[3]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("check_pr_round_cap")
main = _mod.main
build_parser = _mod.build_parser
evaluate_round_cap = _mod.evaluate_round_cap
parse_marker = _mod.parse_marker
render_state_marker = _mod.render_state_marker
render_escalation_comment = _mod.render_escalation_comment
select_latest_state = _mod.select_latest_state
RoundCapStoreError = _mod.RoundCapStoreError


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_defaults_without_env(self, monkeypatch):
        monkeypatch.delenv("PR_AUTOFIX_MAX_ROUNDS", raising=False)
        monkeypatch.delenv("PR_AUTOFIX_MAX_ROUND_HOURS", raising=False)
        args = build_parser().parse_args(["--pull-request", "123"])
        assert args.pull_request == 123
        assert args.max_rounds == 5
        assert args.max_hours == 4.0

    def test_env_var_overrides_default(self, monkeypatch):
        monkeypatch.setenv("PR_AUTOFIX_MAX_ROUNDS", "3")
        monkeypatch.setenv("PR_AUTOFIX_MAX_ROUND_HOURS", "1.5")
        args = build_parser().parse_args(["--pull-request", "1"])
        assert args.max_rounds == 3
        assert args.max_hours == 1.5

    def test_cli_flag_overrides_env(self, monkeypatch):
        monkeypatch.setenv("PR_AUTOFIX_MAX_ROUNDS", "3")
        args = build_parser().parse_args(
            ["--pull-request", "1", "--max-rounds", "10"],
        )
        assert args.max_rounds == 10


# ---------------------------------------------------------------------------
# evaluate_round_cap: the pure decision function
# ---------------------------------------------------------------------------


class TestEvaluateRoundCap:
    def test_first_round_with_no_prior_state_is_act(self):
        now = datetime.now(UTC)
        result = evaluate_round_cap(None, now, max_rounds=5, max_hours=4.0)
        assert result["action"] == "ACT"
        assert result["round"] == 1
        assert result["state"]["first_seen"] == now.isoformat()

    def test_round_below_cap_is_act(self):
        now = datetime.now(UTC)
        state = {"round": 3, "first_seen": now.isoformat(), "last_round_at": now.isoformat()}
        result = evaluate_round_cap(state, now, max_rounds=5, max_hours=4.0)
        assert result["action"] == "ACT"
        assert result["round"] == 4

    def test_round_exactly_at_cap_escalates(self):
        """Cap not yet reached (4/5) proceeds; the 5th recorded round trips it."""
        now = datetime.now(UTC)
        state = {"round": 4, "first_seen": now.isoformat(), "last_round_at": now.isoformat()}
        result = evaluate_round_cap(state, now, max_rounds=5, max_hours=4.0)
        assert result["round"] == 5
        assert result["action"] == "ESCALATE"
        assert "round cap reached" in result["reason"]

    def test_wall_clock_budget_exceeded_independent_of_round_count(self):
        """Round count is well under cap; only the elapsed time is over budget."""
        now = datetime.now(UTC)
        first_seen = now - timedelta(hours=5)
        state = {
            "round": 1,
            "first_seen": first_seen.isoformat(),
            "last_round_at": first_seen.isoformat(),
        }
        result = evaluate_round_cap(state, now, max_rounds=5, max_hours=4.0)
        assert result["round"] == 2  # well under the round cap
        assert result["action"] == "ESCALATE"
        assert "wall-clock budget exceeded" in result["reason"]

    def test_corrupted_first_seen_restarts_clock_instead_of_crashing(self):
        now = datetime.now(UTC)
        state = {"round": 2, "first_seen": "not-a-timestamp", "last_round_at": ""}
        result = evaluate_round_cap(state, now, max_rounds=5, max_hours=4.0)
        assert result["action"] == "ACT"
        assert result["elapsed_hours"] == 0.0

    def test_missing_round_key_treated_as_zero(self):
        now = datetime.now(UTC)
        state = {"first_seen": now.isoformat()}
        result = evaluate_round_cap(state, now, max_rounds=5, max_hours=4.0)
        assert result["round"] == 1


# ---------------------------------------------------------------------------
# Marker parse / render round-trip
# ---------------------------------------------------------------------------


class TestMarkerRoundTrip:
    def test_render_then_parse_round_trips(self):
        state = {
            "round": 2,
            "first_seen": "2026-01-01T00:00:00+00:00",
            "last_round_at": "2026-01-01T01:00:00+00:00",
        }
        body = render_state_marker(state)
        parsed = parse_marker(body, _mod._STATE_MARKER)
        assert parsed == state

    def test_parse_marker_missing_prefix_returns_none(self):
        assert parse_marker("just a regular comment", _mod._STATE_MARKER) is None

    def test_parse_marker_missing_close_token_returns_none(self):
        body = f"{_mod._STATE_MARKER}{{'round': 1}}"  # no closing -->
        assert parse_marker(body, _mod._STATE_MARKER) is None

    def test_parse_marker_malformed_json_returns_none(self):
        body = f"{_mod._STATE_MARKER}not json at all-->"
        assert parse_marker(body, _mod._STATE_MARKER) is None

    def test_state_and_escalation_markers_are_distinct_prefixes(self):
        """A state marker must never be mistaken for an escalation marker."""
        state = {"round": 1, "first_seen": "x", "last_round_at": "y"}
        state_body = render_state_marker(state)
        assert parse_marker(state_body, _mod._ESCALATION_MARKER) is None

    def test_select_latest_state_returns_last_match(self):
        comments = [
            {"body": render_state_marker({"round": 1, "first_seen": "a", "last_round_at": "a"})},
            {"body": "unrelated human comment"},
            {"body": render_state_marker({"round": 2, "first_seen": "a", "last_round_at": "b"})},
        ]
        latest = select_latest_state(comments, _mod._STATE_MARKER)
        assert latest["round"] == 2

    def test_select_latest_state_no_match_returns_none(self):
        assert select_latest_state([{"body": "hello"}], _mod._STATE_MARKER) is None

    def test_render_escalation_comment_carries_marker_and_numbers(self):
        body = render_escalation_comment(
            pr_number=42,
            round_count=5,
            max_rounds=5,
            elapsed_hours=2.3,
            max_hours=4.0,
            reason="round cap reached: 5 rounds recorded (cap: 5)",
        )
        assert _mod._ESCALATION_MARKER in body
        assert "#42" in body
        assert "Rounds recorded: 5 (cap: 5)" in body


# ---------------------------------------------------------------------------
# main(): envelope shape, exit codes, escalation idempotency
# ---------------------------------------------------------------------------


class _MainHarness:
    """Shared patch plumbing for the main() test classes."""

    def teardown_method(self):
        for extra in getattr(self, "_extra", []):
            extra.stop()
        self._extra = []

    def _patch_common(
        self, list_comments_result=None, list_comments_error=None,
        head_sha="sha-1", events=None,
    ):
        self._extra = [
            patch("check_pr_round_cap._fetch_head_sha", return_value=head_sha),
            patch("check_pr_round_cap._list_issue_events", return_value=events or []),
        ]
        for extra in self._extra:
            extra.start()
        patches = [
            patch("check_pr_round_cap.assert_gh_authenticated"),
            patch(
                "check_pr_round_cap.resolve_repo_params",
                return_value=_mod.RepoInfo(owner="o", repo="r"),
            ),
        ]
        if list_comments_error is not None:
            list_patch = patch(
                "check_pr_round_cap._list_comments", side_effect=list_comments_error,
            )
        else:
            list_patch = patch(
                "check_pr_round_cap._list_comments",
                return_value=list_comments_result or [],
            )
        patches.append(list_patch)
        return patches


class TestMain(_MainHarness):
    def test_first_round_acts_and_exits_zero(self, capsys):
        patches = self._patch_common(list_comments_result=[])
        with patches[0], patches[1], patches[2], \
                patch("check_pr_round_cap._post_comment") as post_mock:
            rc = main(["--pull-request", "7", "--output-format", "json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["Success"] is True
        data = out["Data"]
        assert data["action"] == "ACT"
        assert data["round"] == 1
        assert data["pull_request"] == 7
        assert data["escalation_posted"] is False
        # State marker persisted, no escalation comment posted.
        assert post_mock.call_count == 1

    def test_envelope_shape_has_all_documented_fields(self, capsys):
        patches = self._patch_common(list_comments_result=[])
        with patches[0], patches[1], patches[2], patch("check_pr_round_cap._post_comment"):
            main(["--pull-request", "7", "--output-format", "json"])
        out = json.loads(capsys.readouterr().out)
        data = out["Data"]
        expected_keys = {
            "pull_request", "owner", "repo", "round", "max_rounds",
            "elapsed_hours", "max_hours", "first_seen", "action", "reason",
            "escalation_posted",
        }
        assert expected_keys <= data.keys()

    def test_cap_exactly_reached_escalates_and_exits_one(self, capsys):
        now = datetime.now(UTC)
        prior = render_state_marker(
            {"round": 4, "first_seen": now.isoformat(), "last_round_at": now.isoformat()},
        )
        patches = self._patch_common(list_comments_result=[{"body": prior}])
        with patches[0], patches[1], patches[2], \
                patch("check_pr_round_cap._post_comment") as post_mock:
            rc = main([
                "--pull-request", "7", "--max-rounds", "5",
                "--max-hours", "4", "--output-format", "json",
            ])
        assert rc == 1
        out = json.loads(capsys.readouterr().out)
        data = out["Data"]
        assert data["action"] == "ESCALATE"
        assert data["round"] == 5
        assert data["escalation_posted"] is True
        # State marker + escalation notice: two comment posts.
        assert post_mock.call_count == 2

    def test_wall_clock_exceeded_escalates_regardless_of_round_count(self, capsys):
        now = datetime.now(UTC)
        first_seen = now - timedelta(hours=10)
        prior = render_state_marker(
            {
                "round": 1,
                "first_seen": first_seen.isoformat(),
                "last_round_at": first_seen.isoformat(),
            },
        )
        patches = self._patch_common(list_comments_result=[{"body": prior}])
        with patches[0], patches[1], patches[2], patch("check_pr_round_cap._post_comment"):
            rc = main([
                "--pull-request", "7", "--max-rounds", "5",
                "--max-hours", "4", "--output-format", "json",
            ])
        assert rc == 1
        out = json.loads(capsys.readouterr().out)
        data = out["Data"]
        assert data["action"] == "ESCALATE"
        assert data["round"] == 2  # nowhere near the round cap
        assert "wall-clock" in data["reason"]

    def test_escalation_note_not_duplicated_on_repeat_call(self, capsys):
        now = datetime.now(UTC)
        prior_state = render_state_marker(
            {"round": 5, "first_seen": now.isoformat(), "last_round_at": now.isoformat()},
        )
        prior_escalation = (
            f"{_mod._ESCALATION_MARKER}{{}}{_mod._MARKER_CLOSE}\nalready escalated"
        )
        patches = self._patch_common(
            list_comments_result=[{"body": prior_state}, {"body": prior_escalation}],
        )
        with patches[0], patches[1], patches[2], \
                patch("check_pr_round_cap._post_comment") as post_mock:
            rc = main([
                "--pull-request", "7", "--max-rounds", "5",
                "--max-hours", "4", "--output-format", "json",
            ])
        assert rc == 1
        out = json.loads(capsys.readouterr().out)
        assert out["Data"]["escalation_posted"] is False
        # Issue #5477: a repeat blocked call is silent, no state marker either.
        assert post_mock.call_count == 0

    def test_comment_fetch_failure_emits_json_error_envelope_and_exits_three(self, capsys):
        patches = self._patch_common(
            list_comments_error=RoundCapStoreError("comment list exited 1: boom"),
        )
        with patches[0], patches[1], patches[2]:
            with pytest.raises(SystemExit) as exc_info:
                main(["--pull-request", "7", "--output-format", "json"])
        assert exc_info.value.code == 3
        out = json.loads(capsys.readouterr().out)
        assert out["Success"] is False
        assert out["Error"]["Code"] == 3
        assert out["Error"]["Type"] == "ApiError"

    def test_state_persist_failure_emits_json_error_envelope_and_exits_three(self, capsys):
        patches = self._patch_common(list_comments_result=[])
        with patches[0], patches[1], patches[2], patch(
            "check_pr_round_cap._post_comment",
            side_effect=RoundCapStoreError("comment post exited 1: boom"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(["--pull-request", "7", "--output-format", "json"])
        assert exc_info.value.code == 3
        out = json.loads(capsys.readouterr().out)
        assert out["Success"] is False
        assert out["Error"]["Code"] == 3

    def test_escalation_note_post_failure_is_non_fatal(self, capsys):
        """Losing the human-readable note must not crash the gate (issue #5056
        item 4: the state persisted and the ESCALATE verdict must still fire)."""
        now = datetime.now(UTC)
        prior = render_state_marker(
            {"round": 4, "first_seen": now.isoformat(), "last_round_at": now.isoformat()},
        )
        patches = self._patch_common(list_comments_result=[{"body": prior}])

        def _post_side_effect(owner, repo, pr_number, body):
            if _mod._ESCALATION_MARKER in body:
                raise RoundCapStoreError("comment post exited 1: rate limited")
            return None

        with patches[0], patches[1], patches[2], patch(
            "check_pr_round_cap._post_comment", side_effect=_post_side_effect,
        ):
            rc = main([
                "--pull-request", "7", "--max-rounds", "5",
                "--max-hours", "4", "--output-format", "json",
            ])
        assert rc == 1
        out = json.loads(capsys.readouterr().out)
        assert out["Data"]["action"] == "ESCALATE"
        assert out["Data"]["escalation_posted"] is False


# ---------------------------------------------------------------------------
# Issue #5477: wall-clock budget reset and silent repeat blocked calls
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
_OLD = _NOW - timedelta(hours=34)


def _state(round_no=3, first_seen=_OLD, head_sha="sha-1"):
    state = {
        "round": round_no,
        "first_seen": first_seen.isoformat(),
        "last_round_at": first_seen.isoformat(),
    }
    if head_sha is not None:
        state["head_sha"] = head_sha
    return state


def _escalation_comment(first_seen):
    body = render_escalation_comment(
        1, 3, 5, 34.0, 4.0, "r", first_seen=first_seen.isoformat(),
    )
    return {"body": body}


def posted_sink(posted):
    def _sink(_owner, _repo, _pr, body):
        posted.append({"body": body})
    return _sink


def _marker_comment(state, created_at="2026-09-02T00:00:00Z"):
    return {"body": render_state_marker(state), "created_at": created_at}


class TestEvaluateReset:
    def test_stale_budget_with_same_head_escalates(self):
        result = evaluate_round_cap(_state(), _NOW, 5, 4.0, head_sha="sha-1")
        assert result["action"] == "ESCALATE"
        assert "wall-clock" in result["reason"]
        assert result["reset_reason"] is None
        assert result["state"]["first_seen"] == _OLD.isoformat()

    def test_stale_budget_with_advanced_head_acts_and_keeps_round(self):
        result = evaluate_round_cap(_state(), _NOW, 5, 4.0, head_sha="sha-2")
        assert result["action"] == "ACT"
        assert result["round"] == 4  # counter semantics unchanged
        assert result["elapsed_hours"] == 0.0
        assert result["reset_reason"] == "head sha advanced"
        assert result["state"]["first_seen"] == _NOW.isoformat()
        assert result["state"]["head_sha"] == "sha-2"

    def test_legacy_state_without_stored_sha_is_not_an_advance(self):
        result = evaluate_round_cap(_state(head_sha=None), _NOW, 5, 4.0, head_sha="sha-2")
        assert result["action"] == "ESCALATE"
        assert result["state"]["head_sha"] == "sha-2"  # recorded for next time

    def test_unknown_head_keeps_stored_sha_and_does_not_reset(self):
        result = evaluate_round_cap(_state(), _NOW, 5, 4.0, head_sha=None)
        assert result["action"] == "ESCALATE"
        assert result["state"]["head_sha"] == "sha-1"

    def test_advanced_head_does_not_bypass_round_cap(self):
        result = evaluate_round_cap(_state(round_no=4), _NOW, 5, 4.0, head_sha="sha-2")
        assert result["action"] == "ESCALATE"
        assert "round cap" in result["reason"]

    def test_reopen_reset_restarts_clock_only(self):
        result = evaluate_round_cap(
            _state(), _NOW, 5, 4.0, head_sha="sha-1", reset=_mod.Reset("human reopen"),
        )
        assert result["action"] == "ACT"
        assert result["round"] == 4
        assert result["reset_reason"] == "human reopen"

    def test_operator_reset_restarts_clock_and_rounds(self):
        reset = _mod.Reset("operator flag --reset", restart_rounds=True)
        result = evaluate_round_cap(_state(round_no=9), _NOW, 5, 4.0, reset=reset)
        assert result["action"] == "ACT"
        assert result["round"] == 1

    def test_round_cap_reached_independent_of_elapsed_time(self):
        fresh = _state(round_no=4, first_seen=_NOW)
        result = evaluate_round_cap(fresh, _NOW, 5, 4.0, head_sha="sha-1")
        assert result["action"] == "ESCALATE"
        assert "round cap" in result["reason"]


class TestDetectReset:
    def test_no_signal_returns_none(self):
        assert _mod.detect_reset([_marker_comment(_state())], [], False) is None

    def test_no_prior_state_returns_none(self):
        assert _mod.detect_reset([{"body": "hi"}], [], False) is None

    def test_operator_flag_wins(self):
        reset = _mod.detect_reset([], [], True)
        assert reset is not None and reset.restart_rounds is True

    def test_reopen_after_marker_resets_clock_only(self):
        events = [{"event": "reopened", "created_at": "2026-09-02T01:00:00Z",
                   "actor": {"login": "h", "type": "User"}}]
        reset = _mod.detect_reset([_marker_comment(_state())], events, False)
        assert reset == _mod.Reset("human reopen")

    def test_reopen_before_marker_is_consumed(self):
        events = [{"event": "reopened", "created_at": "2026-09-01T01:00:00Z",
                   "actor": {"type": "User"}}]
        assert _mod.detect_reset([_marker_comment(_state())], events, False) is None

    def test_bot_reopen_and_other_events_ignored(self):
        events = [
            {"event": "reopened", "created_at": "2026-09-02T01:00:00Z",
             "actor": {"type": "Bot"}},
            {"event": "closed", "created_at": "2026-09-02T02:00:00Z",
             "actor": {"type": "User"}},
            {"event": "reopened", "actor": {"type": "User"}},  # no timestamp
        ]
        assert _mod.detect_reset([_marker_comment(_state())], events, False) is None

    def test_marker_without_timestamp_ignores_events(self):
        events = [{"event": "reopened", "created_at": "2026-09-02T01:00:00Z",
                   "actor": {"type": "User"}}]
        comments = [{"body": render_state_marker(_state())}]
        assert _mod.detect_reset(comments, events, False) is None

    @pytest.mark.parametrize("body", [
        "/pr-autofix continue",
        "  /PR-AUTOFIX   continue  ",
        "Please resume.\n/pr-autofix continue\nThanks",
    ])
    def test_maintainer_continue_comment_resets_both(self, body):
        comments = [
            _marker_comment(_state()),
            {"body": body, "author_association": "COLLABORATOR", "user": {"type": "User"}},
        ]
        reset = _mod.detect_reset(comments, [], False)
        assert reset is not None and reset.restart_rounds is True

    @pytest.mark.parametrize("comment", [
        {"body": "/pr-autofix continue", "author_association": "MEMBER",
         "user": {"type": "User"}},
        {"body": "/pr-autofix continue", "author_association": "NONE",
         "user": {"type": "User"}},
        {"body": "/pr-autofix continue", "author_association": "OWNER",
         "user": {"type": "Bot"}},
        {"body": "looks fine, please continue", "author_association": "OWNER",
         "user": {"type": "User"}},
        {"body": "not /pr-autofix continue here", "author_association": "OWNER",
         "user": {"type": "User"}},
        {"body": None, "author_association": "OWNER"},
    ])
    def test_non_qualifying_comments_do_not_reset(self, comment):
        comments = [_marker_comment(_state()), comment]
        assert _mod.detect_reset(comments, [], False) is None

    def test_continue_comment_before_latest_marker_is_consumed(self):
        comments = [
            {"body": "/pr-autofix continue", "author_association": "OWNER",
             "user": {"type": "User"}},
            _marker_comment(_state()),
        ]
        assert _mod.detect_reset(comments, [], False) is None


class TestEscalationAlreadyPosted:
    def _esc(self, first_seen=None):
        return {"body": render_escalation_comment(1, 3, 5, 1.0, 4.0, "r", first_seen=first_seen)}

    def test_same_first_seen_matches(self):
        assert _mod.escalation_already_posted([self._esc("F")], "F") is True

    def test_different_first_seen_earns_new_notice(self):
        assert _mod.escalation_already_posted([self._esc("F")], "G") is False

    def test_legacy_notice_without_first_seen_matches(self):
        assert _mod.escalation_already_posted([self._esc(None)], "G") is True

    def test_no_notice_returns_false(self):
        assert _mod.escalation_already_posted([{"body": "x"}], "F") is False

    def test_notice_payload_round_trips_first_seen(self):
        payload = parse_marker(self._esc("F")["body"], _mod._ESCALATION_MARKER)
        assert payload == {"first_seen": "F", "round": 3}


class TestMainReset(_MainHarness):
    def _run(self, capsys, comments, extra_args=(), **kwargs):
        patches = self._patch_common(list_comments_result=comments, **kwargs)
        with patches[0], patches[1], patches[2], \
                patch("check_pr_round_cap._post_comment") as post_mock:
            rc = main([
                "--pull-request", "7", "--max-rounds", "5", "--max-hours", "4",
                "--output-format", "json", *extra_args,
            ])
        return rc, json.loads(capsys.readouterr().out)["Data"], post_mock

    def test_repeated_blocked_calls_post_exactly_one_state_marker(self, capsys):
        """Simulate the timeline across three stale-budget calls."""
        timeline = [_marker_comment(_state(round_no=1))]
        state_markers = 1
        for _ in range(3):
            patches = self._patch_common(list_comments_result=list(timeline))
            posted = []
            with patches[0], patches[1], patches[2], patch(
                "check_pr_round_cap._post_comment",
                side_effect=posted_sink(posted),
            ):
                rc = main([
                    "--pull-request", "7", "--max-rounds", "5", "--max-hours", "4",
                    "--output-format", "json",
                ])
            capsys.readouterr()
            self.teardown_method()
            assert rc == 1
            state_markers += sum(_mod._STATE_MARKER in c["body"] for c in posted)
            timeline.extend(posted)
        assert state_markers == 2  # seed + exactly one on the first blocked call
        escalations = [c for c in timeline if _mod._ESCALATION_MARKER in c["body"]]
        assert len(escalations) == 1

    def test_advanced_head_after_escalation_acts(self, capsys):
        comments = [
            _marker_comment(_state(round_no=3)),
            _escalation_comment(_OLD),
        ]
        rc, data, post_mock = self._run(capsys, comments, head_sha="sha-2")
        assert rc == 0
        assert data["action"] == "ACT"
        assert data["reset_reason"] == "head sha advanced"
        assert post_mock.call_count == 1

    def test_legacy_notice_with_reset_at_round_cap_persists_state(self, capsys):
        legacy = {"body": f"{_mod._ESCALATION_MARKER}{{}}{_mod._MARKER_CLOSE}\nold"}
        comments = [_marker_comment(_state(round_no=4)), legacy]
        rc, data, post_mock = self._run(capsys, comments, head_sha="sha-2")
        assert rc == 1
        assert data["reset_reason"] == "head sha advanced"
        assert post_mock.call_count == 1  # state marker only, no second notice
        assert _mod._STATE_MARKER in post_mock.call_args.args[3]

    def test_reopen_after_escalation_acts(self, capsys):
        comments = [
            _marker_comment(_state(round_no=3)),
            _escalation_comment(_OLD),
        ]
        events = [{"event": "reopened", "created_at": "2026-09-02T01:00:00Z",
                   "actor": {"type": "User"}}]
        rc, data, _ = self._run(capsys, comments, events=events)
        assert rc == 0
        assert data["reset_reason"] == "human reopen"

    def test_reset_flag_restarts_rounds_and_clock(self, capsys):
        comments = [_marker_comment(_state(round_no=9))]
        rc, data, _ = self._run(capsys, comments, extra_args=["--reset"])
        assert rc == 0
        assert data["round"] == 1
        assert data["reset_reason"] == "operator flag --reset"

    def test_sha_and_event_fetch_failures_fail_safe(self, capsys):
        comments = [_marker_comment(_state())]
        patches = self._patch_common(list_comments_result=comments)
        with patches[0], patches[1], patches[2], \
                patch("check_pr_round_cap._fetch_head_sha",
                      side_effect=RoundCapStoreError("boom")), \
                patch("check_pr_round_cap._list_issue_events",
                      side_effect=RoundCapStoreError("boom")), \
                patch("check_pr_round_cap._post_comment"):
            rc = main([
                "--pull-request", "7", "--max-rounds", "5", "--max-hours", "4",
                "--output-format", "json",
            ])
        data = json.loads(capsys.readouterr().out)["Data"]
        assert rc == 1  # stale budget, no reset evidence: still escalates
        assert data["reset_reason"] is None


class TestGhReaders:
    def test_head_sha_returns_trimmed_stdout(self):
        with patch("subprocess.run", return_value=_completed(stdout="abc123\n")):
            assert _mod._fetch_head_sha("o", "r", 1) == "abc123"

    def test_head_sha_empty_output_raises(self):
        with patch("subprocess.run", return_value=_completed(stdout="\n")):
            with pytest.raises(RoundCapStoreError):
                _mod._fetch_head_sha("o", "r", 1)

    def test_nonzero_exit_raises(self):
        with patch("subprocess.run", return_value=_completed(stderr="no", rc=1)):
            with pytest.raises(RoundCapStoreError):
                _mod._list_issue_events("o", "r", 1)

    def test_oserror_raises(self):
        with patch("subprocess.run", side_effect=OSError("gone")):
            with pytest.raises(RoundCapStoreError):
                _mod._fetch_head_sha("o", "r", 1)

    def test_events_parsed_from_paginated_arrays(self):
        out = '[{"event":"reopened"}][{"event":"closed"}]'
        with patch("subprocess.run", return_value=_completed(stdout=out)):
            assert len(_mod._list_issue_events("o", "r", 1)) == 2
