"""Tests for pr_wait.py event diffing, gate evaluation, and settle."""

from __future__ import annotations

from typing import Any

import pytest

from tests.skills.claude_skills_import import import_cached_module

# Load the shared helpers by path, so the test directory never joins sys.path.
_helpers: Any = import_cached_module(
    "tests/skills/pr-babysit/_pr_wait_helpers.py", "_pr_wait_helpers"
)
_gate = _helpers.gate_payload
_node = _helpers.node
_pr = _helpers.pr_payload
pw = _helpers.pw
pwa = _helpers.pwa

# diff_activity


def test_baseline_records_activity_without_events() -> None:
    state = pw.State()
    pr = _pr(comments={"totalCount": 1, "nodes": [_node("c1", "bot")]})

    events = pw.diff_activity(state, pr, "me", baseline=True)

    assert events == []
    assert "c1" in state.seen


def test_new_comment_from_other_user_is_one_event() -> None:
    state = pw.State(totals={"comments": 0})
    pr = _pr(comments={"totalCount": 1, "nodes": [_node("c1", "copilot")]})

    events = pw.diff_activity(state, pr, "me", baseline=False)

    assert events == ["comment: copilot https://x/c1"]


def test_own_and_author_activity_is_ignored() -> None:
    state = pw.State(totals={"comments": 0})
    pr = _pr(
        author={"login": "author"},
        comments={"totalCount": 2, "nodes": [_node("c1", "me"), _node("c2", "Author")]},
    )

    assert pw.diff_activity(state, pr, "me", baseline=False) == []


def test_seen_comment_is_not_reported_twice() -> None:
    state = pw.State(seen={"c1"}, totals={"comments": 1})
    pr = _pr(comments={"totalCount": 1, "nodes": [_node("c1", "bot")]})

    assert pw.diff_activity(state, pr, "me", baseline=False) == []


def test_review_event_includes_state() -> None:
    state = pw.State(totals={"reviews": 0})
    pr = _pr(reviews={"totalCount": 1, "nodes": [_node("r1", "bot", state="COMMENTED")]})

    assert pw.diff_activity(state, pr, "me", baseline=False) == [
        "review: bot COMMENTED https://x/r1"
    ]


def _thread(
    thread_id: str, first: dict[str, Any], last: dict[str, Any], count: int
) -> dict[str, Any]:
    return {
        "id": thread_id,
        "first": {"nodes": [first]},
        "last": {"totalCount": count, "nodes": [last]},
    }


def test_thread_reply_is_reported() -> None:
    state = pw.State(seen={"tc1"}, thread_counts={"t1": 1}, totals={"reviewThreads": 1})
    thread = _thread("t1", _node("tc1", "bot"), _node("tc2", "bot"), 2)
    pr = _pr(reviewThreads={"totalCount": 1, "nodes": [thread]})

    assert pw.diff_activity(state, pr, "me", baseline=False) == ["thread: bot https://x/tc2"]


def test_new_thread_root_is_reported_when_author_replied_last() -> None:
    state = pw.State(totals={"reviewThreads": 0})
    thread = _thread("t1", _node("tc1", "reviewer"), _node("tc2", "me"), 2)
    pr = _pr(reviewThreads={"totalCount": 1, "nodes": [thread]})

    assert pw.diff_activity(state, pr, "me", baseline=False) == ["thread: reviewer https://x/tc1"]


def test_new_thread_with_hidden_middle_replies_reports_activity() -> None:
    state = pw.State(totals={"reviewThreads": 0})
    thread = _thread("t1", _node("tc1", "reviewer"), _node("tc3", "me"), 3)
    pr = _pr(reviewThreads={"totalCount": 1, "nodes": [thread]})

    assert pw.diff_activity(state, pr, "me", baseline=False)[-1].startswith("activity:")


def test_overflow_beyond_window_reports_activity_line() -> None:
    state = pw.State(totals={"comments": 0})
    pr = _pr(comments={"totalCount": 80, "nodes": [_node("c80", "bot")]})

    events = pw.diff_activity(state, pr, "me", baseline=False)

    assert events[-1].startswith("activity:")


def test_skipped_thread_replies_report_activity_line() -> None:
    state = pw.State(seen={"tc1"}, thread_counts={"t1": 1}, totals={"reviewThreads": 1})
    thread = _thread("t1", _node("tc1", "bot"), _node("tc4", "bot"), 4)
    pr = _pr(reviewThreads={"totalCount": 1, "nodes": [thread]})

    assert pw.diff_activity(state, pr, "me", baseline=False)[-1].startswith("activity:")


def test_baseline_warns_when_threads_exceed_window() -> None:
    state = pw.State()
    pr = _pr(reviewThreads={"totalCount": pwa.THREAD_WINDOW + 5, "nodes": []})

    events = pw.diff_activity(state, pr, "me", baseline=True)

    assert events == [
        f"activity: {pwa.THREAD_WINDOW + 5} threads; replies in the oldest 5 are not "
        "watched; read every thread"
    ]


# diff_pr


def test_merged_pr_is_done_zero() -> None:
    poll = pw.diff_pr(pw.State(), _pr(state="MERGED"), False)

    assert (poll.events, poll.done) == (["merged"], 0)


def test_closed_pr_is_done_one() -> None:
    poll = pw.diff_pr(pw.State(), _pr(state="CLOSED"), False)

    assert (poll.events, poll.done, poll.blockers) == (["closed"], 1, {"closed"})


def test_new_head_resets_checks_but_keeps_review_blockers() -> None:
    state = pw.State(
        head="c" * 40, failing={"lint"}, green_head="c" * 40, blockers={"thread:t1", "check:lint"}
    )

    poll = pw.diff_pr(state, _pr(), False)

    assert poll.events == ["head: aaaaaaa"]
    assert (state.failing, state.green_head, state.blockers) == (set(), "", {"thread:t1"})


def test_base_move_is_reported_after_baseline() -> None:
    state = pw.State(head="a" * 40, base_oid="d" * 40)

    assert pw.diff_pr(state, _pr(), False).events == ["base: main moved to bbbbbbb"]


def test_dirty_is_reported_and_blocks() -> None:
    state = pw.State(head="a" * 40, base_oid="b" * 40)

    poll = pw.diff_pr(state, _pr(mergeStateStatus="DIRTY"), False)

    assert poll.events == ["merge-state: DIRTY"]
    assert poll.blockers == {"dirty:aaaaaaa:bbbbbbb"}


def test_behind_is_reported_without_blocker() -> None:
    state = pw.State(head="a" * 40, base_oid="b" * 40)

    poll = pw.diff_pr(state, _pr(mergeStateStatus="BEHIND"), False)

    assert (poll.events, poll.blockers) == (["merge-state: BEHIND"], set())


def test_draft_is_a_blocker() -> None:
    assert pw.diff_pr(pw.State(), _pr(isDraft=True), True).blockers == {"draft"}


# evaluate_gate and settle


def _gate_poll(state: Any, gate: dict[str, Any], until: str, **poll: Any) -> Any:
    result = pw.Poll(**poll)
    pw.evaluate_gate(state, gate, until, result)
    return result


def test_failing_required_check_is_event_and_blocker() -> None:
    state = pw.State(head="a" * 40)

    poll = _gate_poll(state, _gate(FailingRequired=["pytest"]), "ready")

    assert poll.events == ["check: pytest failed on aaaaaaa"]
    assert poll.blockers == {"check:pytest"}


def test_pending_checks_keep_waiting() -> None:
    state = pw.State(head="a" * 40, merge_state="BLOCKED")

    poll = _gate_poll(state, _gate(PendingRequired=["pytest"]), "ready")

    assert (poll.events, poll.blockers, poll.done) == ([], set(), None)


def test_green_until_is_done_on_green() -> None:
    state = pw.State(head="a" * 40)

    poll = _gate_poll(state, _gate(), "green")

    assert poll.events == ["green: required checks passed on aaaaaaa"]
    assert poll.done == 0


def test_green_until_ignores_draft() -> None:
    state = pw.State(head="a" * 40)

    poll = _gate_poll(state, _gate(), "green", blockers={"draft"})

    assert (poll.blockers, poll.done) == (set(), 0)


def test_ready_is_done_when_green_clean_and_no_threads() -> None:
    state = pw.State(head="a" * 40, merge_state="CLEAN")

    assert _gate_poll(state, _gate(), "ready").done == 0


def test_ready_blocks_on_unresolved_threads() -> None:
    state = pw.State(head="a" * 40, merge_state="BLOCKED")

    poll = _gate_poll(state, _gate(UnresolvedThreads=2), "ready", open_threads={"t1", "t2"})

    assert poll.blockers == {"thread:t1", "thread:t2"}


def test_threads_beyond_the_window_block_as_unlisted() -> None:
    state = pw.State(head="a" * 40, merge_state="BLOCKED")

    poll = _gate_poll(state, _gate(UnresolvedThreads=3), "ready", open_threads={"t1"})

    assert poll.blockers == {"thread:t1", "threads:unlisted"}


def test_open_threads_come_from_unresolved_current_snapshot_nodes() -> None:
    threads = {
        "totalCount": 3,
        "nodes": [
            {"id": "t1", "isResolved": False, "isOutdated": False},
            {"id": "t2", "isResolved": True, "isOutdated": False},
            {"id": "t3", "isResolved": False, "isOutdated": True},
        ],
    }

    assert pw.diff_pr(pw.State(), _pr(reviewThreads=threads), True).open_threads == {"t1"}


def test_ready_blocks_on_behind_keyed_by_base() -> None:
    state = pw.State(head="a" * 40, base_oid="b" * 40, merge_state="BEHIND")

    assert _gate_poll(state, _gate(), "ready").blockers == {"behind:bbbbbbb"}


def test_ready_blocks_on_draft_once_green() -> None:
    state = pw.State(head="a" * 40, merge_state="CLEAN")

    poll = _gate_poll(state, _gate(), "ready", blockers={"draft"})

    assert (poll.blockers, poll.done) == ({"draft"}, None)


def test_ready_waits_while_merge_state_unknown() -> None:
    state = pw.State(head="a" * 40, merge_state="UNKNOWN")

    assert _gate_poll(state, _gate(), "ready").done is None


def test_missing_ruleset_requires_overall_success() -> None:
    state = pw.State(head="a" * 40)
    gate = _gate(RulesetContextsAvailable=False, OverallState="PENDING")

    assert _gate_poll(state, gate, "green").done is None


def test_green_reported_once_per_head() -> None:
    state = pw.State(head="a" * 40, green_head="a" * 40)

    assert _gate_poll(state, _gate(), "any-change").events == []


def test_settle_exits_one_on_new_blocker_with_line() -> None:
    state = pw.State()
    poll = pw.Poll(blockers={"thread:t1"})

    assert pw.settle(state, poll, "ready") == 1
    assert poll.events == ["blocked: thread:t1"]


def test_settle_keeps_waiting_on_known_blocker() -> None:
    state = pw.State(blockers={"thread:t1"})
    poll = pw.Poll(blockers={"thread:t1"})

    assert pw.settle(state, poll, "ready") is None
    assert poll.events == []


def test_settle_rearms_blocker_after_it_clears() -> None:
    state = pw.State(blockers={"thread:t1"})
    pw.settle(state, pw.Poll(ready_checked=True), "ready")

    assert pw.settle(state, pw.Poll(blockers={"thread:t1"}), "ready") == 1


def test_settle_closed_exits_one_even_for_any_change() -> None:
    poll = pw.Poll(events=["closed"], blockers={"closed"}, done=1)

    assert pw.settle(pw.State(), poll, "any-change") == 1


def test_changes_requested_is_a_blocker_keyed_by_head() -> None:
    poll = pw.diff_pr(pw.State(), _pr(reviewDecision="CHANGES_REQUESTED"), True)

    assert poll.blockers == {"changes-requested:aaaaaaa"}


def test_green_ignores_review_state() -> None:
    state = pw.State(head="a" * 40)

    poll = _gate_poll(state, _gate(), "green", blockers={"changes-requested:a"})

    assert (poll.blockers, poll.done) == (set(), 0)


def test_green_with_known_dirty_blocker_does_not_exit_zero() -> None:
    state = pw.State(head="a" * 40, blockers={"dirty:aaaaaaa:bbbbbbb"})
    poll = _gate_poll(state, _gate(), "green", blockers={"dirty:aaaaaaa:bbbbbbb"})

    assert poll.done is None
    assert pw.settle(state, poll, "green") is None


def test_head_seen_at_is_set_on_new_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pw.time, "time", lambda: 42.0)
    state = pw.State()

    pw.diff_pr(state, _pr(), True)

    assert state.head_seen_at == 42.0


def test_changes_requested_is_keyed_by_review_id() -> None:
    reviews = {
        "totalCount": 2,
        "nodes": [
            _node("r1", "rev", state="CHANGES_REQUESTED"),
            _node("r2", "rev", state="CHANGES_REQUESTED"),
        ],
    }
    pr = _pr(reviewDecision="CHANGES_REQUESTED", reviews=reviews)

    assert pw.diff_pr(pw.State(), pr, True).blockers == {"changes-requested:r2"}


def test_review_required_is_a_blocker_on_a_green_head() -> None:
    state = pw.State(head="a" * 40, merge_state="BLOCKED")
    blockers = pw.diff_pr(pw.State(head="a" * 40), _pr(reviewDecision="REVIEW_REQUIRED"), True)

    poll = _gate_poll(state, _gate(), "ready", blockers=set(blockers.blockers))

    assert (poll.blockers, poll.done) == ({"review-required"}, None)


def test_absent_required_check_blocks_green_and_ready() -> None:
    for until in ("green", "ready"):
        state = pw.State(head="a" * 40, merge_state="BLOCKED")
        gate = _gate(MissingRequired=["e2e"], AbsentRequired=["e2e"])

        poll = _gate_poll(state, gate, until)

        assert poll.blockers == {"absent:e2e:aaaaaaa"}, until


def test_ready_waits_until_head_seen_for_settle_window(monkeypatch: pytest.MonkeyPatch) -> None:
    state = pw.State(head="a" * 40, merge_state="CLEAN", head_seen_at=1_000.0)
    monkeypatch.setattr(pw.time, "time", lambda: 1_000.0 + pw.SETTLE_SECONDS - 1)

    assert _gate_poll(state, _gate(), "ready").done is None

    monkeypatch.setattr(pw.time, "time", lambda: 1_000.0 + pw.SETTLE_SECONDS)
    assert _gate_poll(state, _gate(), "ready").done == 0


def test_gate_payload_missing_a_key_fails_loud() -> None:
    gate = _gate()
    del gate["FailingRequired"]

    with pytest.raises(RuntimeError, match="FailingRequired"):
        _gate_poll(pw.State(head="a" * 40), gate, "ready")


def test_absent_check_waits_for_grace_after_head_sighting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = pw.State(head="a" * 40, head_seen_at=1_000.0)
    gate = _gate(MissingRequired=["e2e"], AbsentRequired=["e2e"])
    monkeypatch.setattr(pw.time, "time", lambda: 1_000.0 + pw.ABSENT_GRACE_SECONDS - 1)

    assert _gate_poll(state, gate, "green").blockers == set()

    monkeypatch.setattr(pw.time, "time", lambda: 1_000.0 + pw.ABSENT_GRACE_SECONDS)
    assert _gate_poll(state, gate, "green").blockers == {"absent:e2e:aaaaaaa"}


def test_review_blocker_survives_pending_phase_without_rearming() -> None:
    state = pw.State(head="a" * 40, merge_state="BLOCKED", blockers={"changes-requested:r1"})
    pending = _gate_poll(
        state, _gate(PendingRequired=["ci"]), "ready", blockers={"changes-requested:r1"}
    )

    assert pw.settle(state, pending, "ready") is None
    assert "changes-requested:r1" in state.blockers

    green = _gate_poll(state, _gate(), "ready", blockers={"changes-requested:r1"})

    assert pw.settle(state, green, "ready") is None
    assert green.events == ["green: required checks passed on aaaaaaa"]


def test_cleared_review_blocker_is_forgotten_after_green_check() -> None:
    state = pw.State(head="a" * 40, merge_state="BLOCKED", blockers={"thread:t1"})
    pw.settle(state, _gate_poll(state, _gate(), "ready"), "ready")

    assert state.blockers == set()


def _cycle(state: Any, open_threads: set[str]) -> int | None:
    """Push, one pending poll, then a green poll with the given open threads."""
    pw.diff_pr(state, _pr(), False)
    count = len(open_threads)
    pending = _gate_poll(state, _gate(PendingRequired=["ci"], UnresolvedThreads=count), "ready")
    assert pw.settle(state, pending, "ready") is None
    green = _gate_poll(state, _gate(UnresolvedThreads=count), "ready", open_threads=open_threads)
    result: int | None = pw.settle(state, green, "ready")
    return result


def test_new_bot_thread_after_push_fires_again() -> None:
    state = pw.State(head="c" * 40, merge_state="BLOCKED", blockers={"thread:t1"})

    assert _cycle(state, {"t1", "t2"}) == 1


def test_resolve_plus_new_thread_in_one_push_fires() -> None:
    state = pw.State(head="c" * 40, merge_state="BLOCKED", blockers={"thread:t1", "thread:t2"})

    assert _cycle(state, {"t3", "t4"}) == 1


def test_same_unresolved_threads_stay_quiet_across_push() -> None:
    state = pw.State(head="c" * 40, merge_state="BLOCKED", blockers={"thread:t1"})

    assert _cycle(state, {"t1"}) is None


def test_resolving_one_of_two_threads_stays_quiet() -> None:
    state = pw.State(head="c" * 40, merge_state="BLOCKED", blockers={"thread:t1", "thread:t2"})

    assert _cycle(state, {"t2"}) is None
    assert state.blockers == {"thread:t2"}


def test_rerun_recovery_on_same_head_reports_green_again() -> None:
    state = pw.State(head="a" * 40, green_head="a" * 40)

    failed = _gate_poll(state, _gate(FailingRequired=["ci"]), "green")
    recovered = _gate_poll(state, _gate(), "green")

    assert failed.events == ["check: ci failed on aaaaaaa"]
    assert recovered.events == ["green: required checks passed on aaaaaaa"]


def test_ready_exit_prints_a_ready_line() -> None:
    state = pw.State(head="a" * 40, merge_state="CLEAN")

    poll = _gate_poll(state, _gate(), "ready")

    assert poll.events[-1] == "ready: aaaaaaa can merge once the merge gate agrees"
