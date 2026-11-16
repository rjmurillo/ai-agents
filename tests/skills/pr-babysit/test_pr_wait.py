"""Tests for pr_wait.py target parsing, state, lock, and the CLI exit contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _pr_wait_helpers import gate_payload as _gate
from _pr_wait_helpers import node as _node
from _pr_wait_helpers import pr_payload as _pr
from _pr_wait_helpers import pw, pws

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

    assert pw.load_state(path, path.stat().st_mtime + pws.STALE_STATE_SECONDS + 1) is None


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
