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


def test_thread_reply_is_reported() -> None:
    state = pw.State(thread_counts={"t1": 1}, totals={"reviewThreads": 1})
    thread = {"id": "t1", "comments": {"totalCount": 2, "nodes": [_node("tc2", "bot")]}}
    pr = _pr(reviewThreads={"totalCount": 1, "nodes": [thread]})

    assert pw.diff_activity(state, pr, "me", baseline=False) == ["thread: bot https://x/tc2"]


def test_overflow_beyond_window_reports_activity_line() -> None:
    state = pw.State(totals={"comments": 0})
    pr = _pr(comments={"totalCount": 80, "nodes": [_node("c80", "bot")]})

    events = pw.diff_activity(state, pr, "me", baseline=False)

    assert events[-1].startswith("activity:")


def test_skipped_thread_replies_report_activity_line() -> None:
    state = pw.State(thread_counts={"t1": 1}, totals={"reviewThreads": 1})
    thread = {"id": "t1", "comments": {"totalCount": 4, "nodes": [_node("tc4", "bot")]}}
    pr = _pr(reviewThreads={"totalCount": 1, "nodes": [thread]})

    assert pw.diff_activity(state, pr, "me", baseline=False)[-1].startswith("activity:")


# diff_pr


def test_merged_pr_exits_zero() -> None:
    assert pw.diff_pr(pw.State(), _pr(state="MERGED"), False) == (["merged"], 0)


def test_closed_pr_exits_one() -> None:
    assert pw.diff_pr(pw.State(), _pr(state="CLOSED"), False) == (["closed"], 1)


def test_new_head_resets_failing_and_green() -> None:
    state = pw.State(head="c" * 40, failing={"lint"}, green_head="c" * 40)

    events, code = pw.diff_pr(state, _pr(), False)

    assert events == ["head: aaaaaaa"]
    assert code is None
    assert state.failing == set()
    assert state.green_head == ""


def test_base_move_is_reported_after_baseline() -> None:
    state = pw.State(head="a" * 40, base_oid="d" * 40)

    events, _ = pw.diff_pr(state, _pr(), False)

    assert events == ["base: main moved to bbbbbbb"]


def test_dirty_is_reported_once_and_exits_one() -> None:
    state = pw.State(head="a" * 40, base_oid="b" * 40)

    events, code = pw.diff_pr(state, _pr(mergeStateStatus="DIRTY"), False)

    assert events == ["merge-state: DIRTY"]
    assert code == 1


def test_behind_is_reported_without_exit() -> None:
    state = pw.State(head="a" * 40, base_oid="b" * 40)

    events, code = pw.diff_pr(state, _pr(mergeStateStatus="BEHIND"), False)

    assert events == ["merge-state: BEHIND"]
    assert code is None


# evaluate_gate


def test_failing_required_check_exits_one_with_event() -> None:
    state = pw.State(head="a" * 40)

    events, code = pw.evaluate_gate(state, _gate(FailingRequired=["pytest"]), "ready")

    assert events == ["check: pytest failed on aaaaaaa"]
    assert code == 1


def test_pending_checks_keep_waiting() -> None:
    state = pw.State(head="a" * 40, merge_state="BLOCKED")

    assert pw.evaluate_gate(state, _gate(PendingRequired=["pytest"]), "ready") == ([], None)


def test_green_until_exits_zero_on_green() -> None:
    state = pw.State(head="a" * 40)

    events, code = pw.evaluate_gate(state, _gate(), "green")

    assert events == ["green: required checks passed on aaaaaaa"]
    assert code == 0


def test_ready_exits_zero_when_green_clean_and_no_threads() -> None:
    state = pw.State(head="a" * 40, merge_state="CLEAN")

    assert pw.evaluate_gate(state, _gate(), "ready")[1] == 0


def test_ready_exits_one_when_unresolved_threads_remain() -> None:
    state = pw.State(head="a" * 40, merge_state="BLOCKED")

    assert pw.evaluate_gate(state, _gate(UnresolvedThreads=2), "ready")[1] == 1


def test_ready_exits_one_when_behind() -> None:
    state = pw.State(head="a" * 40, merge_state="BEHIND")

    assert pw.evaluate_gate(state, _gate(), "ready")[1] == 1


def test_ready_waits_while_merge_state_unknown() -> None:
    state = pw.State(head="a" * 40, merge_state="UNKNOWN")

    assert pw.evaluate_gate(state, _gate(), "ready")[1] is None


def test_missing_ruleset_requires_overall_success() -> None:
    state = pw.State(head="a" * 40)
    gate = _gate(RulesetContextsAvailable=False, OverallState="PENDING")

    assert pw.evaluate_gate(state, gate, "green") == ([], None)


def test_green_reported_once_per_head() -> None:
    state = pw.State(head="a" * 40, green_head="a" * 40)

    assert pw.evaluate_gate(state, _gate(), "any-change") == ([], None)


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
