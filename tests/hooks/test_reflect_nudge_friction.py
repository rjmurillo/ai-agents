"""Friction branch of the reflect nudge: threshold, tiers, markers, merge (REQ-048 TASK-003).

Covers AC-07 to AC-13, AC-20, AC-23. Budget and bound tests live in
test_reflect_nudge_friction_budget.py.
"""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Any

import pytest

from tests.hooks.friction_nudge_support import (
    PLANT,
    THRESHOLD_ENV,
    expected_score,
    friction_records,
    run_env,
    write_transcript,
)
from tests.hooks.reflect_nudge_support import human, nudge, nudge_state

fc = nudge.failure_classifier

STATE_DIR = "ai-agents-reflect-nudge"
OFF_VALUES = ["0", "off", "OFF", "Off", "  0  ", "\toff\n", " oFf "]


def markers(state: Path) -> list[Path]:
    directory = state / STATE_DIR
    return sorted(directory.iterdir()) if directory.exists() else []


def message(out: str) -> str:
    doc = json.loads(out)
    assert set(doc) == {"systemMessage"}
    return str(doc["systemMessage"])


@pytest.fixture
def friction10(tmp_path: Path) -> Path:
    """Score 11 (4 denials, 1 feedback): tier 1 at the default threshold 10."""
    assert expected_score(4, 1) == 11
    return write_transcript(tmp_path / "f.jsonl", friction_records(denials=4, feedback=1))


class TestOff:
    @pytest.mark.parametrize("raw", OFF_VALUES)
    def test_off_runs_nothing_from_either_branch(
        self, raw: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        both = write_transcript(
            tmp_path / "t.jsonl", [human("no, wrong"), *friction_records(denials=6)]
        )

        def forbidden(*_a: Any, **_k: Any) -> Any:
            raise AssertionError("off must not touch stdin, transcript, or state")

        monkeypatch.setattr(nudge, "open_transcript", forbidden)
        monkeypatch.setattr(nudge, "read_payload", forbidden)
        monkeypatch.setattr(nudge, "safe_marker_dir", forbidden)
        state = tmp_path / "state"
        code, out, err = run_env(both, state, {THRESHOLD_ENV: raw})
        assert (code, out, err) == (0, "", "")
        assert not state.exists()

    def test_positive_control_same_transcript_fires_when_not_off(self, tmp_path: Path) -> None:
        both = write_transcript(
            tmp_path / "t.jsonl", [human("no, wrong"), *friction_records(denials=6)]
        )
        for raw in ("00", "+0", "-0"):
            state = tmp_path / f"s{raw}"
            _, out, _ = run_env(both, state, {THRESHOLD_ENV: raw})
            assert "/reflect" in message(out) and "/retrospective" in message(out)


class TestFrictionNudge:
    def test_fires_once_with_fixed_template(self, friction10: Path, tmp_path: Path) -> None:
        state = tmp_path / "state"
        code, out, err = run_env(friction10, state)
        text = message(out)
        assert code == 0
        assert out.count("\n") == 1
        assert "/retrospective" in text
        assert "score 11, tier 1" in text and "4 permission denial" in text
        assert "1 Stop hook feedback" in text and "error streak of 1" in text
        assert "You can run" in text and "friction score 11 tier 1" in err
        assert "decision" not in out and "block" not in out

    def test_no_transcript_text_in_any_output_or_marker(
        self, friction10: Path, tmp_path: Path
    ) -> None:
        state = tmp_path / "state"
        _, out, err = run_env(friction10, state)
        assert PLANT in friction10.read_text(encoding="utf-8")
        assert PLANT not in out + err
        assert all(PLANT not in m.read_text(encoding="utf-8") for m in markers(state))

    def test_template_is_fixed_across_inputs(self, tmp_path: Path) -> None:
        a = write_transcript(tmp_path / "a.jsonl", friction_records(denials=5, feedback=0))
        b = write_transcript(tmp_path / "b.jsonl", friction_records(denials=2, feedback=4))
        _, out_a, _ = run_env(a, tmp_path / "sa")
        _, out_b, _ = run_env(b, tmp_path / "sb")
        shape = [re.sub(r"\d+", "N", message(o)) for o in (out_a, out_b)]
        assert shape[0] == shape[1]

    def test_message_addresses_user_and_gives_agent_no_instruction(
        self, friction10: Path, tmp_path: Path
    ) -> None:
        _, out, _ = run_env(friction10, tmp_path / "state")
        text = message(out)
        assert text.startswith("reflect-trigger: ")
        assert not re.search(r"\b(you must|do not|don't|claude|assistant|agent)\b", text, re.I)

    def test_below_threshold_is_silent_and_writes_no_state(self, tmp_path: Path) -> None:
        path = write_transcript(tmp_path / "t.jsonl", friction_records(denials=4))
        assert expected_score(4, 0) == 9
        state = tmp_path / "state"
        code, out, err = run_env(path, state)
        assert (code, out) == (0, "")
        assert "silent" in err and "friction score 9 tier 0" in err
        assert not state.exists()

    def test_env_threshold_lowers_tier_one(self, tmp_path: Path) -> None:
        path = write_transcript(tmp_path / "t.jsonl", friction_records(denials=1))
        _, quiet, _ = run_env(path, tmp_path / "s1")
        _, loud, _ = run_env(path, tmp_path / "s2", {THRESHOLD_ENV: "3"})
        assert quiet == "" and "tier 1" in message(loud)

    def test_sidechain_records_do_not_count(self, tmp_path: Path) -> None:
        from tests.hooks.friction_nudge_support import DENIAL_TEXT, call, stop_feedback

        records: list[Any] = []
        for index in range(10):
            records += call(f"s{index}", error=DENIAL_TEXT, sidechain=True)
        records.append(stop_feedback(sidechain=True))
        path = write_transcript(tmp_path / "t.jsonl", records)
        _, out, _ = run_env(path, tmp_path / "state")
        assert out == ""

    def test_negative_threshold_value_uses_default(self, friction10: Path, tmp_path: Path) -> None:
        _, out, _ = run_env(friction10, tmp_path / "state", {THRESHOLD_ENV: "-3"})
        assert "tier 1" in message(out)


class TestTierEscalation:
    def test_new_tier_fires_once_and_repeat_stop_does_not(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        env = {THRESHOLD_ENV: "4"}
        path = tmp_path / "t.jsonl"
        write_transcript(path, friction_records(denials=2))  # score 5, tier 1
        _, first, _ = run_env(path, state, env)
        _, repeat, err = run_env(path, state, env)
        assert "tier 1" in message(first)
        assert repeat == "" and "already nudged" in err
        write_transcript(path, friction_records(denials=4))  # score 9, tier 2
        _, second, _ = run_env(path, state, env)
        _, again, _ = run_env(path, state, env)
        assert "tier 2" in message(second) and again == ""
        write_transcript(path, friction_records(denials=8))  # score 17, tier 3
        _, third, _ = run_env(path, state, env)
        assert "tier 3" in message(third)
        assert len(markers(state)) == 3

    def test_jump_to_a_high_tier_claims_only_that_tier(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        path = write_transcript(tmp_path / "t.jsonl", friction_records(denials=8))
        _, out, _ = run_env(path, state, {THRESHOLD_ENV: "4"})
        assert "tier 3" in message(out)
        assert len(markers(state)) == 1

    def test_sessions_do_not_share_markers(self, friction10: Path, tmp_path: Path) -> None:
        state = tmp_path / "state"
        _, a, _ = run_env(friction10, state, session_id="sess-a")
        _, b, _ = run_env(friction10, state, session_id="sess-b")
        assert "tier 1" in message(a) and "tier 1" in message(b)


class TestMarkers:
    def test_friction_marker_mode_dir_mode_and_counts_only_body(
        self, friction10: Path, tmp_path: Path
    ) -> None:
        state = tmp_path / "state"
        run_env(friction10, state)
        (marker,) = markers(state)
        assert marker.name == fc.friction_marker_name("sess-1", 1, nudge.MARKER_VERSION)
        if os.name != "nt":
            assert stat.S_IMODE(marker.stat().st_mode) == 0o600
            assert stat.S_IMODE((state / STATE_DIR).stat().st_mode) == 0o700
        body = json.loads(marker.read_text(encoding="utf-8"))
        assert body == {
            "v": nudge.MARKER_VERSION,
            "tier": 1,
            "score": 11,
            "denials": 4,
            "stop_feedback": 1,
            "streak": 1,
        }

    def test_marker_names_differ_per_tier_and_session(self) -> None:
        names = {fc.friction_marker_name(s, t, 1) for s in ("a", "b") for t in (1, 2)}
        assert len(names) == 4

    def test_friction_marker_is_separate_from_correction_marker(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        path = write_transcript(tmp_path / "t.jsonl", [human("no, wrong"), *friction_records(6)])
        run_env(path, state)
        names = [m.name for m in markers(state)]
        assert len(names) == 2
        assert sum("friction-" in n for n in names) == 1

    def test_old_friction_markers_are_pruned_like_correction_markers(
        self, friction10: Path, tmp_path: Path
    ) -> None:
        state = tmp_path / "state"
        run_env(friction10, state, session_id="old")
        (old,) = markers(state)
        long_ago = old.stat().st_mtime - nudge_state.MARKER_MAX_AGE_SECONDS - 10
        os.utime(old, (long_ago, long_ago))
        run_env(friction10, state, session_id="new")
        assert [m.name for m in markers(state)] == [
            fc.friction_marker_name("new", 1, nudge.MARKER_VERSION)
        ]


class TestBothBranches:
    def test_one_document_carries_both_messages(self, tmp_path: Path) -> None:
        path = write_transcript(tmp_path / "t.jsonl", [human("no, wrong"), *friction_records(6)])
        code, out, err = run_env(path, tmp_path / "state")
        text = message(out)
        assert code == 0 and out.count("\n") == 1
        assert "/reflect" in text and "/retrospective" in text
        assert "(nudged" in err and "friction score" in err

    def test_new_correction_with_same_tier_fires_no_second_friction_nudge(
        self, tmp_path: Path
    ) -> None:
        state = tmp_path / "state"
        path = tmp_path / "t.jsonl"
        write_transcript(path, friction_records(6))
        _, first, _ = run_env(path, state)
        write_transcript(path, [*friction_records(6), human("no, wrong")])
        _, second, _ = run_env(path, state)
        assert "/retrospective" in message(first)
        assert "/reflect" in message(second) and "/retrospective" not in message(second)
        write_transcript(path, [*friction_records(6), human("no, wrong"), human("that's wrong")])
        _, third, _ = run_env(path, state)
        assert "/retrospective" not in message(third)

    def test_correction_only_keeps_its_message_shape(self, tmp_path: Path) -> None:
        path = write_transcript(tmp_path / "t.jsonl", [human("no, wrong"), human("perfect")])
        _, out, _ = run_env(path, tmp_path / "state")
        text = message(out)
        assert "1 correction and 1 praise or preference" in text
        assert "/retrospective" not in text and "You can run /reflect" in text


class TestCorrectionPositiveControl:
    @pytest.mark.parametrize("env", [{}, {THRESHOLD_ENV: "7"}, {THRESHOLD_ENV: "-1"}])
    def test_correction_still_fires(self, env: dict[str, str], tmp_path: Path) -> None:
        path = write_transcript(tmp_path / "t.jsonl", [human("No, use the other one")])
        code, out, _ = run_env(path, tmp_path / "state", env)
        assert code == 0 and "/reflect" in message(out)
