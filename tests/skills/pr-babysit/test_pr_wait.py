"""Tests for pr-babysit's pr_wait.py event watcher."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "claude"
    / "skills"
    / "pr-babysit"
    / "scripts"
    / "pr_wait.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("pr_wait", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["pr_wait"] = module
    spec.loader.exec_module(module)
    return module


pw = _load()


def _node(node_id: str, login: str, **extra: Any) -> dict[str, Any]:
    return {"id": node_id, "url": f"https://x/{node_id}", "author": {"login": login}, **extra}


def _pr(**overrides: Any) -> dict[str, Any]:
    pr: dict[str, Any] = {
        "state": "OPEN",
        "headRefOid": "a" * 40,
        "baseRefName": "main",
        "baseRefOid": "b" * 40,
        "mergeStateStatus": "BLOCKED",
        "author": {"login": "me"},
        "comments": {"totalCount": 0, "nodes": []},
        "reviews": {"totalCount": 0, "nodes": []},
        "reviewThreads": {"totalCount": 0, "nodes": []},
    }
    pr.update(overrides)
    return pr


def _gate(**overrides: Any) -> dict[str, Any]:
    gate: dict[str, Any] = {
        "FailingRequired": [],
        "PendingRequired": [],
        "MissingRequired": [],
        "IndeterminateRequired": [],
        "UnresolvedThreads": 0,
        "RulesetContextsAvailable": True,
        "OverallState": "SUCCESS",
    }
    gate.update(overrides)
    return gate


# parse_target


def test_parse_target_reads_owner_repo_number_from_url() -> None:
    assert pw.parse_target("https://github.com/o/r/pull/12", None) == ("o", "r", 12)


def test_parse_target_uses_repo_flag_with_number() -> None:
    assert pw.parse_target("7", "o/r") == ("o", "r", 7)


@pytest.mark.parametrize(
    ("raw", "repo"),
    [("abc", "o/r"), ("0", "o/r"), ("7", "bad"), ("https://github.com/o/r/pull/1", "x/y")],
)
def test_parse_target_rejects_bad_input(raw: str, repo: str) -> None:
    with pytest.raises(ValueError):
        pw.parse_target(raw, repo)


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


def _thread(thread_id: str, first: dict[str, Any], last: dict[str, Any], count: int) -> dict:
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


# state and lock


def test_state_round_trips_through_json(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    state = pw.State(head="h", seen={"x"}, thread_counts={"t": 2}, failing={"f"})

    pw.save_state(path, state)
    loaded = pw.load_state(path, path.stat().st_mtime)

    assert loaded == state


def test_stale_state_starts_fresh_baseline(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    pw.save_state(path, pw.State(head="h"))

    assert pw.load_state(path, path.stat().st_mtime + pw.STALE_STATE_SECONDS + 1) is None


def test_corrupt_state_starts_fresh_baseline(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    path.write_text("{not json", encoding="utf-8")

    assert pw.load_state(path, path.stat().st_mtime) is None


def test_second_lock_on_same_pr_is_refused(tmp_path: Path) -> None:
    first = pw.acquire_lock(tmp_path / "pr.lock")
    try:
        assert first is not None
        assert pw.acquire_lock(tmp_path / "pr.lock") is None
    finally:
        assert first is not None
        first.close()


# run loop and exit codes


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(pw, "state_dir", lambda: tmp_path)
    monkeypatch.setattr(pw.time, "sleep", lambda _s: None)
    return tmp_path


def test_main_exits_two_on_bad_target(isolated_state: Path) -> None:
    assert pw.main(["not-a-pr", "--repo", "o/r"]) == 2


def test_main_exits_two_when_another_watcher_holds_lock(isolated_state: Path) -> None:
    held = pw.acquire_lock(isolated_state / "o__r__5.lock")
    try:
        assert pw.main(["5", "--repo", "o/r"]) == 2
    finally:
        assert held is not None
        held.close()


def test_main_exits_zero_when_ready(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(pw, "fetch_snapshot", lambda *_a: (_pr(mergeStateStatus="CLEAN"), "me"))
    monkeypatch.setattr(pw, "fetch_gate", lambda *_a: _gate())

    assert pw.main(["5", "--repo", "o/r"]) == 0
    assert "green: required checks passed" in capsys.readouterr().out


def test_main_exits_one_on_failed_check(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pw, "fetch_snapshot", lambda *_a: (_pr(), "me"))
    monkeypatch.setattr(pw, "fetch_gate", lambda *_a: _gate(FailingRequired=["lint"]))

    assert pw.main(["5", "--repo", "o/r"]) == 1


def test_main_exits_two_when_pr_not_found(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(*_a: Any) -> Any:
        raise LookupError("PR o/r#5 not found")

    monkeypatch.setattr(pw, "fetch_snapshot", missing)

    assert pw.main(["5", "--repo", "o/r"]) == 2


def test_main_exits_three_after_repeated_api_failures(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = {"n": 0}

    def broken(*_a: Any) -> Any:
        calls["n"] += 1
        raise RuntimeError("API rate limit exceeded")

    monkeypatch.setattr(pw, "fetch_snapshot", broken)

    assert pw.main(["5", "--repo", "o/r"]) == 3
    assert calls["n"] == pw.MAX_FAILED_POLLS
    assert capsys.readouterr().out.startswith("unreachable:")


def test_main_reports_activity_then_exits_on_any_change(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshots = iter(
        [
            _pr(),
            _pr(comments={"totalCount": 1, "nodes": [_node("c1", "copilot")]}),
        ]
    )
    monkeypatch.setattr(pw, "fetch_snapshot", lambda *_a: (next(snapshots), "me"))
    monkeypatch.setattr(pw, "fetch_gate", lambda *_a: _gate(PendingRequired=["pytest"]))

    assert pw.main(["5", "--repo", "o/r", "--until", "any-change"]) == 0
    assert capsys.readouterr().out.strip() == "comment: copilot https://x/c1"


def test_restart_reports_what_arrived_between_runs(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pw.save_state(
        isolated_state / "o__r__5.json",
        pw.State(head="a" * 40, base_oid="b" * 40, totals={"comments": 0}),
    )
    pr = _pr(comments={"totalCount": 1, "nodes": [_node("c9", "bot")]})
    monkeypatch.setattr(pw, "fetch_snapshot", lambda *_a: (pr, "me"))
    monkeypatch.setattr(pw, "fetch_gate", lambda *_a: _gate(FailingRequired=["x"]))

    assert pw.main(["5", "--repo", "o/r"]) == 1
    out = capsys.readouterr().out
    assert "comment: bot https://x/c9" in out


def test_fetch_gate_raises_on_script_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        returncode = 3
        stdout = ""
        stderr = "API error"

    monkeypatch.setattr(pw.subprocess, "run", lambda *_a, **_k: Result())

    with pytest.raises(RuntimeError, match="exit 3"):
        pw.fetch_gate("o", "r", 5)


def test_fetch_gate_returns_data_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        returncode = 1
        stdout = json.dumps({"Data": {"HasBlocker": True}})
        stderr = ""

    monkeypatch.setattr(pw.subprocess, "run", lambda *_a, **_k: Result())

    assert pw.fetch_gate("o", "r", 5) == {"HasBlocker": True}


def test_why_pr_blocked_sibling_path_exists() -> None:
    assert pw.why_pr_blocked_path().is_file()


def test_restart_with_known_blocker_waits_until_ready(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pw.save_state(
        isolated_state / "o__r__5.json",
        pw.State(head="a" * 40, base_oid="b" * 40, green_head="a" * 40, blockers={"threads"}),
    )
    gates = iter([_gate(UnresolvedThreads=1), _gate(UnresolvedThreads=0)])
    monkeypatch.setattr(pw, "fetch_snapshot", lambda *_a: (_pr(mergeStateStatus="CLEAN"), "me"))
    monkeypatch.setattr(pw, "fetch_gate", lambda *_a: next(gates))

    assert pw.main(["5", "--repo", "o/r"]) == 0
    assert capsys.readouterr().out == ""


def test_main_exits_two_on_graphql_not_found(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import github_core.api as api

    def not_found(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError(
            "GraphQL error: Could not resolve to a PullRequest with the number of 9."
        )

    monkeypatch.setattr(api, "gh_graphql", not_found)

    assert pw.main(["9", "--repo", "o/r"]) == 2


def test_main_exits_four_on_auth_failure(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pw, "fetch_snapshot", lambda *_a: (_pr(), "me"))

    def no_auth(*_a: Any) -> Any:
        raise pw.AuthError("not logged in")

    monkeypatch.setattr(pw, "fetch_gate", no_auth)

    assert pw.main(["5", "--repo", "o/r"]) == 4


@pytest.mark.parametrize(("code", "error"), [(2, LookupError), (4, "AuthError")])
def test_fetch_gate_maps_permanent_exits(
    monkeypatch: pytest.MonkeyPatch, code: int, error: Any
) -> None:
    class Result:
        returncode = code
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(pw.subprocess, "run", lambda *_a, **_k: Result())
    expected = getattr(pw, error) if isinstance(error, str) else error

    with pytest.raises(expected):
        pw.fetch_gate("o", "r", 5)


def test_state_key_is_case_insensitive() -> None:
    assert pw.state_key("Foo", "Bar", 5) == pw.state_key("foo", "bar", 5)
