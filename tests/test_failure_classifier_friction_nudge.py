"""Pure friction-nudge logic in scripts/failure_classifier/friction.py (REQ-048 TASK-003).

Covers AC-11 to AC-13 (threshold), the FrictionTier rule, AC-07 (message), AC-09
(marker key), AC-43 (one definition), and the event-cap helper.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

import pytest

from scripts import failure_classifier as fc
from scripts.failure_classifier import friction as module
from tests.hooks.friction_nudge_support import DENIAL_TEXT, call, friction_records, stop_feedback

ENV = fc.THRESHOLD_ENV
OFF_VALUES = ["0", "off", "OFF", "Off", "  0  ", "\toff\n", " oFf ", "\n0\t"]
NOT_OFF_DEFAULTS = ["00", "+0", "-0", "-5", "abc", "1.5", "", "1_0", "５", "0x5", "off0", "o ff"]


class TestParseThreshold:
    @pytest.mark.parametrize("raw", OFF_VALUES)
    def test_off_values_return_none(self, raw: str) -> None:
        assert fc.parse_threshold({ENV: raw}) is None

    @pytest.mark.parametrize("raw", NOT_OFF_DEFAULTS)
    def test_not_off_and_not_positive_uses_default(self, raw: str) -> None:
        assert fc.parse_threshold({ENV: raw}) == fc.FRICTION_TIER1_DEFAULT

    @pytest.mark.parametrize(("raw", "value"), [("5", 5), (" 7 ", 7), ("+3", 3), ("1", 1)])
    def test_positive_integer_sets_tier_one(self, raw: str, value: int) -> None:
        assert fc.parse_threshold({ENV: raw}) == value

    def test_unset_uses_default_and_honors_an_explicit_default(self) -> None:
        assert fc.parse_threshold({}) == fc.FRICTION_TIER1_DEFAULT == 10
        assert fc.parse_threshold({}, 4) == 4
        assert fc.parse_threshold({ENV: "-1"}, 4) == 4

    def test_huge_digit_string_does_not_crash(self) -> None:
        assert fc.parse_threshold({ENV: "9" * 5000}) == fc.FRICTION_TIER1_DEFAULT

    def test_reads_no_other_key(self) -> None:
        assert fc.parse_threshold({"OTHER": "off"}) == fc.FRICTION_TIER1_DEFAULT


class TestTier:
    @pytest.mark.parametrize(
        ("score", "tier"),
        [(0, 0), (3, 0), (4, 1), (7, 1), (8, 2), (15, 2), (16, 3), (32, 4)],
    )
    def test_tier_n_needs_threshold_times_two_to_n_minus_one(self, score: int, tier: int) -> None:
        assert fc.friction_tier(score, 4) == tier

    def test_tier_is_bounded(self) -> None:
        assert fc.friction_tier(10**30, 1) == module.MAX_TIER


class TestComputeFriction:
    def test_scores_with_the_shared_weights(self) -> None:
        friction = fc.compute_friction(friction_records(denials=4, feedback=1), 10)
        assert friction == fc.Friction(score=11, tier=1, denials=4, stop_feedback=1, streak=1)
        assert fc.FRICTION_WEIGHTS["permission_denial"] == 2

    def test_empty_records_score_zero(self) -> None:
        assert fc.compute_friction([], 10) == fc.Friction(0, 0, 0, 0, 0)

    def test_sidechain_records_are_not_counted(self) -> None:
        records = [*call("a", error=DENIAL_TEXT, sidechain=True), stop_feedback(sidechain=True)]
        assert fc.compute_friction(records, 1).score == 0

    def test_accepts_a_generator(self) -> None:
        records = (r for r in friction_records(denials=1))
        assert fc.compute_friction(records, 1).denials == 1


class TestCollectRecord:
    def test_keeps_conversation_records(self) -> None:
        kept: list[Mapping[str, Any]] = []
        assert fc.collect_record(kept, {"type": "user"}, 5) == 0
        assert fc.collect_record(kept, {"type": "assistant"}, 5) == 0
        assert len(kept) == 2

    @pytest.mark.parametrize(
        "record", [{"type": "summary"}, {"type": "user", "isSidechain": True}, {}]
    )
    def test_ignores_other_records_without_counting_them_dropped(
        self, record: dict[str, Any]
    ) -> None:
        kept: list[Mapping[str, Any]] = []
        assert fc.collect_record(kept, record, 5) == 0 and kept == []

    def test_cap_drops_and_reports_one(self) -> None:
        kept: list[Mapping[str, Any]] = [{"type": "user"}]
        assert fc.collect_record(kept, {"type": "user"}, 1) == 1
        assert len(kept) == 1

    def test_cap_does_not_count_ignored_records(self) -> None:
        kept: list[Mapping[str, Any]] = [{"type": "user"}]
        assert fc.collect_record(kept, {"type": "summary"}, 1) == 0

    def test_non_true_sidechain_values_are_kept(self) -> None:
        assert fc.keeps_record({"type": "user", "isSidechain": False})
        assert fc.keeps_record({"type": "user", "isSidechain": None})


class TestStatus:
    @pytest.mark.parametrize(
        ("stopped", "dropped", "budget"),
        [("", 0, ""), ("time", 0, "time"), ("bytes", 3, "bytes"), ("", 3, "events")],
    )
    def test_partial_budget(self, stopped: str, dropped: int, budget: str) -> None:
        assert fc.partial_budget(stopped, dropped) == budget

    def test_status_names_the_budget(self) -> None:
        friction = fc.Friction(11, 1, 4, 1, 1)
        assert fc.friction_status("time", 0, friction) == ", friction skipped: time budget"
        assert fc.friction_status("", 2, friction) == ", friction skipped: events budget"

    def test_status_reports_the_score_otherwise(self) -> None:
        assert fc.friction_status("", 0, fc.Friction(11, 1, 4, 1, 1)) == (
            ", friction score 11 tier 1"
        )
        assert fc.friction_status("", 0, None) == ""


class TestMarkerAndMessage:
    def test_marker_name_is_keyed_on_session_version_and_tier(self) -> None:
        names = {
            fc.friction_marker_name(s, t, v) for s in ("a", "b") for t in (1, 2) for v in (1, 2)
        }
        assert len(names) == 8
        assert fc.friction_marker_name("a", 1, 1) == fc.friction_marker_name("a", 1, 1)
        assert re.fullmatch(r"a\.friction-[0-9a-f]{16}\.json", fc.friction_marker_name("a", 1, 1))

    def test_marker_body_holds_counts_only(self) -> None:
        body = fc.friction_marker_body(fc.Friction(11, 1, 4, 1, 1), 1)
        assert body == {
            "v": 1,
            "score": 11,
            "tier": 1,
            "denials": 4,
            "stop_feedback": 1,
            "streak": 1,
        }
        assert all(isinstance(v, int) for v in body.values())
        json.dumps(body)

    def test_message_names_retrospective_and_all_four_counts(self) -> None:
        text = fc.build_friction_message(fc.Friction(11, 1, 4, 2, 3), "pfx")
        assert text.startswith("pfx: ") and "/retrospective" in text
        assert "score 11" in text and "4 permission" in text and "2 Stop hook" in text
        assert "streak of 3" in text and "You can run" in text

    def test_message_carries_no_agent_instruction(self) -> None:
        text = fc.build_friction_message(fc.Friction(11, 1, 4, 2, 3), "pfx")
        assert not re.search(r"\b(you must|do not|don't|claude|assistant|agent)\b", text, re.I)


@pytest.mark.parametrize(
    "raw",
    ["0", "off", "OFF", " off ", "\t0\n", "00", "+0", "-0", "5", "-3", "junk", "", "0.0", "o ff"],
)
def test_hook_off_check_agrees_with_parse_threshold(
    raw: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hook's lib-free off check and the classifier's parser share one off grammar."""
    import sys

    monkeypatch.setattr(sys, "dont_write_bytecode", True)  # keep templates/ clean
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "templates/hooks/Stop/_reflect_nudge_state.py"
    spec = importlib.util.spec_from_file_location("_reflect_nudge_state_probe", path)
    assert spec is not None and spec.loader is not None
    state = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(state)
    env = {state.THRESHOLD_ENV: raw}
    assert state.is_off(env) is (module.parse_threshold(env) is None)
