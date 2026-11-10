"""Opt-in timeline supplementation and strata in session_sampling (epic #7248, M2)."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any

import audit_scores
import pytest
from session_sampling import (
    NON_PROBABILITY_NOTE,
    SKILL_FIRST,
    TIMELINE_SUPPLEMENT,
    apply_strata,
    evenly_spaced,
    sample_sessions,
)

Row = dict[str, Any]
TABLES = audit_scores.load_label_tables()
# sha256 of the old (pre-M2) sample_sessions output on the fixture in _golden_rows(),
# computed from `git show 687190fa4:.../session_sampling.py` before the change.
OLD_GOLDEN = "f1bf35ae5897b1396e3dd405f37a9e2d1a7b94ccf090c532418f19c519bfe4c1"


# ------------------------------------------------- timeline supplementation


def _golden_rows() -> list[Row]:
    return [
        {
            "harness": "claude" if i % 2 == 0 else "codex",
            "_key": f"k{i}",
            "modified_at": f"2026-11-0{i + 1}T00:00:00Z",
            "skills_used": ["a"] if i < 3 else [],
        }
        for i in range(6)
    ]


def _digest_of(sampled: set[str], per_harness: Any, sampling: Any) -> str:
    blob = json.dumps([sorted(sampled), per_harness, sampling], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def test_option_off_matches_the_output_of_the_pre_change_sampler() -> None:
    sessions = _golden_rows()
    absent = SimpleNamespace(max_sessions=4, per_skill=1, no_skill=1)
    zero = SimpleNamespace(max_sessions=4, per_skill=1, no_skill=1, timeline_supplement=0)

    off_absent = sample_sessions(sessions, {"a": {}}, absent)
    off_zero = sample_sessions(sessions, {"a": {}}, zero)

    assert _digest_of(*off_absent) == OLD_GOLDEN
    assert _digest_of(*off_zero) == OLD_GOLDEN
    assert "strata" not in off_zero[2] and "representative" not in off_zero[2]


def _on(count: int, sessions: list[Row] | None = None) -> tuple[Any, Any, Any]:
    args = SimpleNamespace(max_sessions=4, per_skill=1, no_skill=1, timeline_supplement=count)
    return sample_sessions(sessions or _golden_rows(), {"a": {}}, args)


def test_option_on_keeps_the_existing_picks_and_adds_only_no_skill_sessions() -> None:
    base = sample_sessions(
        _golden_rows(), {"a": {}}, SimpleNamespace(max_sessions=4, per_skill=1, no_skill=1)
    )[0]

    sampled, _, sampling = _on(1)

    added = sampled - base
    assert base <= sampled
    assert len(added) == 1
    assert added <= {"k3", "k4", "k5"}
    assert sampling["stratum_members"][TIMELINE_SUPPLEMENT] == sorted(added)
    assert sampling["stratum_members"][SKILL_FIRST] == sorted(base)


def test_option_on_records_strata_counts_rules_and_non_probability_note() -> None:
    _, per_harness, sampling = _on(2)

    assert sampling["representative"] is False
    assert sampling["non_probability_note"] == NON_PROBABILITY_NOTE
    assert sampling["timeline_supplement"]["requested"] == 2
    candidates = sampling["strata"][TIMELINE_SUPPLEMENT]["candidates"]
    assert sampling["timeline_supplement"]["added"] == min(2, candidates) >= 1
    strata = sampling["strata"]
    assert strata[SKILL_FIRST]["candidates"] == 6
    assert strata[TIMELINE_SUPPLEMENT]["candidates"] >= strata[TIMELINE_SUPPLEMENT]["selected"]
    assert strata[TIMELINE_SUPPLEMENT]["rule"] and strata[SKILL_FIRST]["rule"]
    assert sum(entry.get("supplemented", 0) for entry in per_harness.values()) == min(2, candidates)


def test_supplement_is_deterministic_and_spaced_over_the_window() -> None:
    sessions = [
        {
            "harness": "h",
            "_key": f"n{i:02d}",
            "modified_at": f"2026-11-{i + 1:02d}T00:00:00Z",
            "skills_used": [],
        }
        for i in range(9)
    ]
    args = SimpleNamespace(max_sessions=0, per_skill=1, no_skill=0, timeline_supplement=3)

    first = sample_sessions(sessions, {}, args)[0]
    second = sample_sessions(list(reversed(sessions)), {}, args)[0]

    assert first == second == {"n00", "n04", "n08"}


def test_supplement_larger_than_pool_takes_every_candidate_and_zero_pool_adds_none() -> None:
    sampled, _, sampling = _on(50)
    assert sampled >= {"k3", "k4", "k5"}
    assert sampling["timeline_supplement"]["added"] <= 3

    only_skilled = [row for row in _golden_rows() if row["skills_used"]]
    sampled, _, sampling = _on(5, only_skilled)
    assert sampling["timeline_supplement"]["added"] == 0
    assert sampling["strata"][TIMELINE_SUPPLEMENT]["candidates"] == 0
    assert sampling["representative"] is False


def test_negative_count_is_treated_as_off() -> None:
    assert _digest_of(*_on(-2)) == OLD_GOLDEN


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, []), (1, [2]), (2, [0, 4]), (3, [0, 2, 4]), (5, [0, 1, 2, 3, 4]), (9, [0, 1, 2, 3, 4])],
)
def test_evenly_spaced_ranks(count: int, expected: list[int]) -> None:
    assert evenly_spaced([0, 1, 2, 3, 4], count) == expected


def test_evenly_spaced_empty_pool() -> None:
    assert evenly_spaced([], 3) == []


def test_apply_strata_tags_sessions_and_is_a_noop_without_members() -> None:
    sessions = [{"_key": "a"}, {"_key": "b"}, {"_key": "c"}]

    apply_strata(sessions, {})
    assert all("stratum" not in s for s in sessions)

    members = {SKILL_FIRST: ["a"], TIMELINE_SUPPLEMENT: ["b"]}
    apply_strata(sessions, {"stratum_members": members})
    assert [s.get("stratum") for s in sessions] == [SKILL_FIRST, TIMELINE_SUPPLEMENT, None]
