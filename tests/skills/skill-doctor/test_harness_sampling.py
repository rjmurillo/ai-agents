"""Harness-aware sampling: the cap is split across harnesses, never filled by one (issue #7187)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from session_sampling import (
    SAMPLING_RULE,
    WITHIN_HARNESS_RULE,
    harness_quotas,
    sample_sessions,
)
from session_test_helpers import run_collector, write_jsonl

FIXED = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc).timestamp()
ROOTS = ["claude", "copilot-cli"]
EMPTY = "no-such-home"


def _claude_session(claude_home: Path, repo: Path, session_id: str, mtime: float) -> None:
    common = {
        "sessionId": session_id,
        "cwd": str(repo),
        "timestamp": "2026-11-09T12:00:00Z",
        "version": "1.0.0",
    }
    path = claude_home / "projects" / "repo" / f"{session_id}.jsonl"
    write_jsonl(
        path,
        [
            {**common, "type": "user", "uuid": "u1", "message": {"role": "user", "content": "Fix"}},
            {
                **common,
                "type": "assistant",
                "uuid": "a1",
                "message": {
                    "id": "m1",
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Reading."},
                        {"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}},
                    ],
                },
            },
        ],
    )
    os.utime(path, (mtime, mtime))


def _copilot_session(home: Path, repo: Path, session_id: str, mtime: float) -> None:
    def event(kind: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"type": kind, "timestamp": "2026-11-09T12:00:00Z", "data": data}

    path = home / "session-state" / session_id / "events.jsonl"
    write_jsonl(
        path,
        [
            event("session.start", {"sessionId": session_id, "context": {"cwd": str(repo)}}),
            event("user.message", {"content": "Fix the parser."}),
            event(
                "assistant.message",
                {
                    "content": "Reading.",
                    "toolRequests": [
                        {"toolCallId": "one", "name": "view", "arguments": {"path": "a.py"}}
                    ],
                },
            ),
            event(
                "tool.execution_start",
                {"toolCallId": "one", "toolName": "view", "arguments": {"path": "a.py"}},
            ),
            event(
                "tool.execution_complete",
                {"toolCallId": "one", "success": True, "result": {"content": "ok"}},
            ),
        ],
    )
    os.utime(path, (mtime, mtime))


def _run(tmp_path: Path, root: str, *extra: str):
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    result = run_collector(
        tmp_path,
        tmp_path / "copilot",
        "--repo",
        str(repo),
        "--claude-home",
        str(tmp_path / "claude"),
        "--codex-home",
        str(tmp_path / EMPTY),
        "--days",
        "36500",
        *extra,
        root=root,
    )
    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text(encoding="utf-8"))
    return inventory, result


def _two_harness_fixture(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _claude_session(tmp_path / "claude", repo, "claude-session", FIXED)
    _copilot_session(tmp_path / "copilot", repo, "copilot-session", FIXED)


def _sampled(inventory) -> list[str]:
    return sorted(
        f"{s['harness']}:{s['meta']['id']}" for s in inventory["sessions"] if s["sampled"]
    )


@pytest.mark.parametrize("root", ROOTS)
def test_cap_below_harness_count_samples_one_conversation_and_names_the_omission(tmp_path, root):
    _two_harness_fixture(tmp_path)

    inventory, result = _run(tmp_path, root, "--max-sessions", "1")

    assert inventory["stats"]["sessions_considered"] == 2
    assert inventory["stats"]["sessions_sampled"] == 1
    assert len(list((tmp_path / "report" / "transcripts").glob("*.md"))) == 1
    assert _sampled(inventory) == ["claude:claude-session"]
    sampling = inventory["sampling"]
    assert sampling["harness_coverage_complete"] is False
    assert sampling["omitted_harnesses"] == [{"harness": "copilot", "scoreable": 1}]
    assert "copilot" in sampling["notice"] and "--max-sessions 1" in sampling["notice"]
    assert sampling["rule"] == SAMPLING_RULE
    assert inventory["stats"]["per_harness"]["copilot"]["sampled"] == 0
    assert inventory["stats"]["per_harness"]["claude"]["sampled"] == 1
    assert "copilot" in result.stderr


@pytest.mark.parametrize("root", ROOTS)
def test_cap_of_two_samples_both_harnesses(tmp_path, root):
    _two_harness_fixture(tmp_path)

    inventory, result = _run(tmp_path, root, "--max-sessions", "2")

    assert _sampled(inventory) == ["claude:claude-session", "copilot:copilot-session"]
    assert inventory["sampling"]["harness_coverage_complete"] is True
    assert inventory["sampling"]["omitted_harnesses"] == []
    assert inventory["sampling"]["notice"] is None
    assert "omitted" not in result.stderr


def test_empty_harness_consumes_no_quota(tmp_path):
    _two_harness_fixture(tmp_path)

    inventory, _ = _run(tmp_path, "claude", "--max-sessions", "2")

    per_harness = inventory["stats"]["per_harness"]
    assert sorted(per_harness) == ["claude", "copilot"]
    assert sum(entry["quota"] for entry in per_harness.values()) == 2
    assert inventory["stats"]["sessions_sampled"] == 2


def test_identical_input_gives_identical_selection(tmp_path):
    _two_harness_fixture(tmp_path)

    first, _ = _run(tmp_path, "claude", "--max-sessions", "1")
    second, _ = _run(tmp_path, "claude", "--max-sessions", "1")

    assert _sampled(first) == _sampled(second) == ["claude:claude-session"]
    assert first["sampling"]["omitted_harnesses"] == second["sampling"]["omitted_harnesses"]


def _row(harness: str, name: str, skills: list[str] | None = None) -> dict[str, Any]:
    return {"harness": harness, "_key": f"{harness}:{name}", "skills_used": skills or []}


def _args(max_sessions: int = 12, per_skill: int = 3, no_skill: int = 4):
    from types import SimpleNamespace

    return SimpleNamespace(max_sessions=max_sessions, per_skill=per_skill, no_skill=no_skill)


def test_unequal_pools_both_appear_and_the_total_cap_holds():
    sessions = [_row("claude", f"c{i}") for i in range(30)]
    sessions += [_row("codex", f"x{i}") for i in range(3)]

    sampled, per_harness, sampling = sample_sessions(
        sessions, {}, _args(max_sessions=12, no_skill=12)
    )

    assert len(sampled) == 12
    assert per_harness["codex"]["sampled"] == 3
    assert per_harness["claude"]["sampled"] == 9
    assert sampling["omitted_harnesses"] == []


def test_default_cap_stays_the_total_cap_across_four_harnesses():
    harnesses = ("claude", "codex", "copilot", "droid")
    sessions = [_row(h, f"{h}{i}") for h in harnesses for i in range(20)]

    sampled, per_harness, _ = sample_sessions(sessions, {}, _args())

    assert len(sampled) <= 12
    assert all(entry["sampled"] > 0 for entry in per_harness.values())


def test_selection_ignores_the_order_harnesses_arrive_in():
    blocks = {h: [_row(h, f"{h}{i}") for i in range(4)] for h in ("claude", "codex", "copilot")}
    forward = [s for h in ("claude", "codex", "copilot") for s in blocks[h]]
    backward = [s for h in ("copilot", "codex", "claude") for s in blocks[h]]

    first = sample_sessions(forward, {}, _args(max_sessions=2))
    second = sample_sessions(backward, {}, _args(max_sessions=2))

    assert first == second


def test_cap_below_harness_count_ranks_by_pool_then_name():
    sessions = [_row("zeta", "z1"), _row("alpha", "a1"), _row("big", "b1"), _row("big", "b2")]

    sampled, _, sampling = sample_sessions(sessions, {}, _args(max_sessions=2))

    assert sampled == {"big:b1", "alpha:a1"}
    assert sampling["omitted_harnesses"] == [{"harness": "zeta", "scoreable": 1}]


def test_zero_cap_omits_every_harness_and_samples_nothing():
    sampled, _, sampling = sample_sessions([_row("claude", "c1")], {}, _args(max_sessions=0))

    assert sampled == set()
    assert sampling["harness_coverage_complete"] is False


def test_no_sessions_means_complete_coverage_of_nothing():
    sampled, per_harness, sampling = sample_sessions([], {}, _args())

    assert sampled == set()
    assert per_harness == {}
    assert sampling["harness_coverage_complete"] is True


def test_skill_first_selection_is_disclosed_per_harness():
    sessions = [
        _row("claude", "recent-plain"),
        _row("claude", "older-skilled", ["alpha"]),
        _row("copilot", "only"),
    ]

    sampled, per_harness, sampling = sample_sessions(sessions, {"alpha": {}}, _args(max_sessions=2))

    assert sampled == {"claude:older-skilled", "copilot:only"}
    assert per_harness["claude"] == {
        "scoreable": 2,
        "skill_candidates": 1,
        "quota": 1,
        "sampled": 1,
        "sampled_with_skills": 1,
    }
    assert per_harness["copilot"]["skill_candidates"] == 0
    assert "skill" in sampling["within_harness"]


def test_quotas_deal_round_robin_and_never_exceed_a_pool():
    assert harness_quotas({"a": 1, "b": 1}, 1) == {"a": 1, "b": 0}
    assert harness_quotas({"a": 1, "b": 1}, 2) == {"a": 1, "b": 1}
    assert harness_quotas({"a": 30, "b": 3}, 12) == {"a": 9, "b": 3}
    assert harness_quotas({"a": 2}, 50) == {"a": 2}
    assert harness_quotas({}, 5) == {}
    assert harness_quotas({"a": 3}, -1) == {"a": 0}


def test_skill_documents_the_deterministic_rule_verbatim():
    skill = Path(__file__).resolve().parents[3] / "src" / "claude" / "skills" / "skill-doctor"
    text = (skill / "SKILL.md").read_text(encoding="utf-8")

    assert SAMPLING_RULE in text
    assert WITHIN_HARNESS_RULE in text
    assert "the cap prevented full harness coverage" in text


def _stable(inventory: dict[str, Any]) -> str:
    return json.dumps({k: v for k, v in inventory.items() if k != "generated_at"}, sort_keys=True)


def test_timeline_supplement_zero_leaves_the_inventory_unchanged(tmp_path):
    root = "claude"
    _two_harness_fixture(tmp_path)

    default, _ = _run(tmp_path, root, "--max-sessions", "1")
    explicit_off, _ = _run(tmp_path, root, "--max-sessions", "1", "--timeline-supplement", "0")

    assert _stable(default) == _stable(explicit_off)
    assert "strata" not in default["sampling"]
    assert all("stratum" not in session for session in default["sessions"])


def test_timeline_supplement_adds_a_tagged_no_skill_session_and_keeps_the_omission_notice(
    tmp_path,
):
    _two_harness_fixture(tmp_path)

    inventory, _ = _run(tmp_path, "claude", "--max-sessions", "1", "--timeline-supplement", "1")

    assert _sampled(inventory) == ["claude:claude-session", "copilot:copilot-session"]
    strata = {f"{s['harness']}:{s['meta']['id']}": s.get("stratum") for s in inventory["sessions"]}
    assert strata == {
        "claude:claude-session": "skill_first",
        "copilot:copilot-session": "timeline_supplement",
    }
    sampling = inventory["sampling"]
    assert sampling["representative"] is False
    assert sampling["strata"]["timeline_supplement"]["candidates"] == 1
    assert sampling["strata"]["timeline_supplement"]["selected"] == 1
    assert sampling["omitted_harnesses"] == [{"harness": "copilot", "scoreable": 1}]
    assert inventory["stats"]["sessions_sampled"] == 2
    assert len(list((tmp_path / "report" / "transcripts").glob("*.md"))) == 2
