"""Top-level reservation: subagent sessions cannot crowd top-level sessions out of the cap."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import audit_manifest as am
import pytest
from session_discovery import parse_collector_args
from session_sampling import TOP_LEVEL_RULE, sample_sessions
from test_subagent_collection import collect, write_claude


def _row(name: str, thread: str, skills: list[str] | None = None, harness: str = "claude"):
    return {
        "harness": harness,
        "_key": f"{harness}:{name}",
        "skills_used": skills or [],
        "thread": thread,
    }


def _args(**overrides: Any) -> SimpleNamespace:
    values = {"max_sessions": 10, "per_skill": 3, "no_skill": 4, "top_level_quota": 4}
    values.update(overrides)
    return SimpleNamespace(**values)


def _children(count: int, skill: str = "review") -> list[dict[str, Any]]:
    return [_row(f"s{i}", "subagent", [skill]) for i in range(count)]


def _tops(count: int, skill: str | None = None) -> list[dict[str, Any]]:
    return [_row(f"t{i}", "top_level", [skill] if skill else []) for i in range(count)]


def test_reserved_slots_keep_top_level_sessions_that_subagents_would_crowd_out():
    # Newest first: 30 subagent sessions sit ahead of the 3 top-level ones.
    sessions = _children(30, "alpha") + _tops(3, "alpha")
    pooled, _, _ = sample_sessions(sessions, {"alpha": {}}, _args(top_level_quota=0))
    assert not {key for key in pooled if key.startswith("claude:t")}

    sampled, _, sampling = sample_sessions(sessions, {"alpha": {}}, _args())
    assert {"claude:t0", "claude:t1", "claude:t2"} <= sampled
    assert sampling["top_level_sampled"] == 3
    assert sampling["top_level_rule"] == TOP_LEVEL_RULE


def test_unused_reserved_slots_go_to_subagent_sessions():
    sessions = _tops(2) + _children(20)
    sampled, per_harness, sampling = sample_sessions(sessions, {"review": {}}, _args(per_skill=20))
    assert len(sampled) == 10
    assert sampling["top_level_reserved"] == 4
    assert sampling["top_level_sampled"] == 2
    assert sampling["subagent_slots"] == 8
    assert per_harness["claude"]["sampled"] == 10


def test_reserved_slots_backfill_past_per_skill_and_no_skill_caps():
    # Six top-level sessions share one skill; per-skill 1 alone would keep one.
    children = [_row(f"s{i}", "subagent") for i in range(10)]
    sampled, per_harness, sampling = sample_sessions(
        _tops(6, "review") + children,
        {"review": {}},
        _args(per_skill=1, no_skill=10, top_level_quota=5),
    )
    top = sorted(key for key in sampled if key.startswith("claude:t"))
    assert top == [f"claude:t{i}" for i in range(5)]
    assert sampling["top_level_sampled"] == 5
    assert len(sampled) == 10
    assert per_harness["claude"]["sampled_with_skills"] == 5


def test_slots_subagents_leave_open_return_to_top_level_sessions():
    # One subagent session cannot fill the five slots left after the reservation.
    sampled, _, sampling = sample_sessions(
        _tops(8) + _children(1), {"review": {}}, _args(max_sessions=7, top_level_quota=2)
    )
    assert len(sampled) == 7
    assert "claude:s0" in sampled
    assert sampling["top_level_sampled"] == 6


def test_reservation_never_exceeds_the_total_cap():
    sampled, _, sampling = sample_sessions(
        _tops(8) + _children(8), {}, _args(max_sessions=3, top_level_quota=40)
    )
    assert len(sampled) == 3
    assert sampling["top_level_reserved"] == 3
    assert sampling["subagent_slots"] == 0
    assert all(key.startswith("claude:t") for key in sampled)


def test_zero_quota_keeps_the_pooled_sampling_block():
    _, _, sampling = sample_sessions(_tops(2) + _children(2), {}, _args(top_level_quota=0))
    assert "top_level_quota" not in sampling
    assert "top_level_rule" not in sampling


def test_missing_thread_counts_as_top_level():
    rows = [{"harness": "claude", "_key": f"claude:n{i}", "skills_used": []} for i in range(3)]
    sampled, _, sampling = sample_sessions(rows, {}, _args(top_level_quota=2, max_sessions=3))
    assert len(sampled) == 3
    assert sampling["top_level_sampled"] == 3
    assert sampling["subagent_slots"] == 1


def test_harness_without_top_level_sessions_still_gets_subagent_slots():
    sessions = _tops(4) + [_row(f"x{i}", "subagent", harness="codex") for i in range(4)]
    sampled, per_harness, sampling = sample_sessions(sessions, {}, _args(max_sessions=6))
    assert per_harness["codex"]["sampled"] == 2
    assert sampling["harness_coverage_complete"] is True
    assert len(sampled) == 6


def _parse(monkeypatch, *argv: str):
    monkeypatch.setattr("sys.argv", ["collect_sessions.py", *argv])
    return parse_collector_args(None)


def test_cli_defaults_match_the_calibrated_values(monkeypatch):
    args = _parse(monkeypatch)
    assert (args.days, args.max_sessions, args.top_level_quota) == (14, 100, 40)
    assert (args.per_skill, args.no_skill) == (10, 20)


@pytest.mark.parametrize("value", ["-1", "two"])
def test_cli_rejects_a_bad_top_level_quota(value, capsys, monkeypatch):
    with pytest.raises(SystemExit) as raised:
        _parse(monkeypatch, "--top-level-quota", value)
    assert raised.value.code == 2
    assert "--top-level-quota" in capsys.readouterr().err


def test_manifest_records_the_top_level_quota(monkeypatch):
    args = _parse(monkeypatch, "--top-level-quota", "7")
    assert am.inputs_from_args(args)["top_level_quota"] == 7
    assert "top_level_quota" in am._CAP_KEYS


def test_collector_reserves_the_parent_when_children_fill_the_cap(tmp_path):
    home = tmp_path / "claude-home"
    write_claude(home, "s1", str(tmp_path))
    inventory, _ = collect(
        tmp_path,
        "--claude-home",
        str(home),
        "--repo",
        str(tmp_path),
        "--max-sessions",
        "1",
        "--top-level-quota",
        "1",
    )
    sampled = [s["thread"] for s in inventory["sessions"] if s["sampled"]]
    assert sampled == ["top_level"]
    assert inventory["sampling"]["top_level_sampled"] == 1
    json.dumps(inventory["sampling"])
