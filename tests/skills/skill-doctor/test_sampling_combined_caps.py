"""Top-level reservation: --per-skill and --no-skill bind across both session types combined."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from session_sampling import sample_sessions

Row = dict[str, Any]


def _row(name: str, thread: str, skills: list[str] | None = None, harness: str = "claude") -> Row:
    return {
        "harness": harness,
        "_key": f"{harness}:{name}",
        "skills_used": skills or [],
        "thread": thread,
    }


def _args(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "max_sessions": 100,
        "per_skill": 10,
        "no_skill": 20,
        "top_level_quota": 40,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _tops(count: int, skill: str | None = None, harness: str = "claude") -> list[Row]:
    return [_row(f"t{i}", "top_level", [skill] if skill else [], harness) for i in range(count)]


def _children(count: int, skill: str | None = None, harness: str = "claude") -> list[Row]:
    return [_row(f"s{i}", "subagent", [skill] if skill else [], harness) for i in range(count)]


def _picked(sessions: list[Row], keys: set[str]) -> list[Row]:
    return [session for session in sessions if session["_key"] in keys]


def test_no_skill_cap_binds_across_top_level_and_subagent_sessions() -> None:
    # Default caps: 20 top-level and 40 subagent sessions, none using a skill.
    sessions = _tops(20) + _children(40)
    sampled, per_harness, _ = sample_sessions(sessions, {}, _args())
    assert len(sampled) == 20
    assert per_harness["claude"]["sampled"] == 20


def test_per_skill_cap_binds_across_top_level_and_subagent_sessions() -> None:
    sessions = _tops(3, "alpha") + _children(5, "alpha")
    sampled, _, _ = sample_sessions(sessions, {"alpha": {}}, _args(per_skill=3, top_level_quota=4))
    assert len(sampled) == 3
    assert {key for key in sampled if key.startswith("claude:t")} == {
        "claude:t0",
        "claude:t1",
        "claude:t2",
    }


def test_returned_top_level_slots_respect_caps_the_subagent_pass_used() -> None:
    # Subagents take 7 of the 12 no-skill slots, so top-level sessions may only add 5 past
    # the reservation of 5.
    sessions = _tops(10) + _children(10)
    sampled, _, sampling = sample_sessions(sessions, {}, _args(no_skill=12, top_level_quota=5))
    assert len(sampled) == 12
    assert sampling["top_level_sampled"] == 5


def test_caps_are_counted_per_harness_not_across_harnesses() -> None:
    sessions = _tops(6) + _children(6) + _tops(6, harness="codex") + _children(6, harness="codex")
    sampled, per_harness, _ = sample_sessions(sessions, {}, _args(no_skill=4, top_level_quota=6))
    assert len(_picked(sessions, sampled)) == 8
    assert per_harness["claude"]["sampled"] == 4
    assert per_harness["codex"]["sampled"] == 4


def test_reserved_backfill_still_passes_the_caps_and_blocks_subagents_on_that_skill() -> None:
    # Backfill puts five alpha top-level sessions in the sample past per-skill 1.
    # Subagent sessions that use alpha add nothing; no-skill subagent sessions still fit.
    sessions = _tops(6, "alpha") + _children(3, "alpha") + [_row("n0", "subagent")]
    sampled, _, _ = sample_sessions(
        sessions, {"alpha": {}}, _args(per_skill=1, no_skill=5, top_level_quota=5)
    )
    assert {key for key in sampled if key.startswith("claude:s")} == set()
    assert "claude:n0" in sampled
    assert len([key for key in sampled if key.startswith("claude:t")]) == 5


def test_pooled_path_is_unchanged_by_a_zero_quota() -> None:
    sessions = _tops(20) + _children(40)
    sampled, _, sampling = sample_sessions(sessions, {}, _args(top_level_quota=0))
    assert len(sampled) == 20
    assert "top_level_rule" not in sampling


def _notice(sessions: list[Row], **overrides: Any) -> str | None:
    _, _, sampling = sample_sessions(sessions, {}, _args(**overrides))
    notice: str | None = sampling["notice"]
    return notice


def test_notice_names_the_reservation_when_it_took_every_slot() -> None:
    # 12 slots, 2 harnesses: the cap fits both, but the reservation gave all 12 to claude.
    sessions = _tops(12) + _children(5, harness="codex")
    notice = _notice(sessions, max_sessions=12, top_level_quota=12, no_skill=20)
    assert notice is not None
    assert "--top-level-quota 12 reserved 12 of the --max-sessions 12 slots" in notice
    assert "codex (5 scoreable)" in notice
    assert "is lower than" not in notice


def test_notice_blames_the_cap_when_it_is_below_the_harness_count() -> None:
    sessions = _tops(3) + _tops(3, harness="codex") + _tops(3, harness="cursor")
    notice = _notice(sessions, max_sessions=2, top_level_quota=2)
    assert notice is not None
    assert "--max-sessions 2 is lower than the 3 harnesses" in notice


def test_notice_blames_the_cap_on_the_pooled_path() -> None:
    sessions = _tops(3) + _tops(3, harness="codex") + _tops(3, harness="cursor")
    notice = _notice(sessions, max_sessions=2, top_level_quota=0)
    assert notice is not None
    assert "--max-sessions 2 is lower than the 3 harnesses" in notice


def test_notice_is_absent_when_every_harness_has_a_slot() -> None:
    sessions = _tops(4) + _children(4, harness="codex")
    assert _notice(sessions, max_sessions=6, top_level_quota=4) is None
