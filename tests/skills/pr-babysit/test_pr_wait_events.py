"""Tests for pr_wait.py event diffing, gate evaluation, and settle."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _pr_wait_helpers import gate_payload as _gate
from _pr_wait_helpers import node as _node
from _pr_wait_helpers import pr_payload as _pr
from _pr_wait_helpers import pw

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
    pr = _pr(reviewThreads={"totalCount": pw.THREAD_WINDOW + 5, "nodes": []})

    events = pw.diff_activity(state, pr, "me", baseline=True)

    assert events == [
        f"activity: {pw.THREAD_WINDOW + 5} threads; replies in the oldest 5 are not "
        "watched; read every thread"
    ]


# diff_pr


def test_merged_pr_is_done_zero() -> None:
    poll = pw.diff_pr(pw.State(), _pr(state="MERGED"), False)

    assert (poll.events, poll.done) == (["merged"], 0)


def test_closed_pr_is_done_one() -> None:
    poll = pw.diff_pr(pw.State(), _pr(state="CLOSED"), False)

    assert (poll.events, poll.done, poll.blockers) == (["closed"], 1, {"closed"})


def test_new_head_resets_failing_green_and_blockers() -> None:
    state = pw.State(head="c" * 40, failing={"lint"}, green_head="c" * 40, blockers={"threads"})

    poll = pw.diff_pr(state, _pr(), False)

    assert poll.events == ["head: aaaaaaa"]
    assert (state.failing, state.green_head, state.blockers) == (set(), "", set())


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

    assert _gate_poll(state, _gate(UnresolvedThreads=2), "ready").blockers == {"threads"}


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
    poll = pw.Poll(blockers={"threads"})

    assert pw.settle(state, poll, "ready") == 1
    assert poll.events == ["blocked: threads"]


def test_settle_keeps_waiting_on_known_blocker() -> None:
    state = pw.State(blockers={"threads"})
    poll = pw.Poll(blockers={"threads"})

    assert pw.settle(state, poll, "ready") is None
    assert poll.events == []


def test_settle_rearms_blocker_after_it_clears() -> None:
    state = pw.State(blockers={"threads"})
    pw.settle(state, pw.Poll(), "ready")

    assert pw.settle(state, pw.Poll(blockers={"threads"}), "ready") == 1


def test_settle_closed_exits_one_even_for_any_change() -> None:
    poll = pw.Poll(events=["closed"], blockers={"closed"}, done=1)

    assert pw.settle(pw.State(), poll, "any-change") == 1
