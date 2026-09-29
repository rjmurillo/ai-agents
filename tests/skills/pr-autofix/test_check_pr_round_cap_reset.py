"""Tests for the check_pr_round_cap.py wall-clock reset (issue #5477).

The budget restarts on head SHA advance, human reopen, or operator reset, and a
repeat blocked call posts nothing. See github_core/round_cap.py.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from round_cap_harness import MainHarness, _completed, _mod

main = _mod.main
build_parser = _mod.build_parser
evaluate_round_cap = _mod.evaluate_round_cap
parse_marker = _mod.parse_marker
render_state_marker = _mod.render_state_marker
render_escalation_comment = _mod.render_escalation_comment
select_latest_state = _mod.select_latest_state
RoundCapStoreError = _mod.RoundCapStoreError


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


class TestMainReset(MainHarness):
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
