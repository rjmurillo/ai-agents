"""Tests for the REQ-048 candidate friction features (positive, negative, edge)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.failure_classifier import FailureEvent, failure_fingerprint, is_denial
from scripts.metrics import friction_calibration_features as feat
from scripts.metrics import friction_calibration_scan as scan
from tests.metrics.friction_calibration_helpers import call, human, write

NEAR_A = "I fixed the failing build by updating the lockfile and re-running the install step."
NEAR_B = "I fixed the failing build by updating the lockfile and re-running the install steps."
FAR = "Completely different message about the weather and an unrelated topic today."


def prose(text: str, kind: str = "text") -> dict[str, Any]:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": kind, "text": text}]},
    }


def stops_of(tmp_path: Path, records: list[Any]) -> list[dict[str, Any]]:
    outcome = scan.scan_session(write(tmp_path / "s.jsonl", records), seed=1)
    assert outcome.row is not None
    return outcome.row["stops"]


def final(tmp_path: Path, records: list[Any], key: str) -> int:
    return stops_of(tmp_path, records)[-1][key]


def ev(error: str, tool: str = "Bash", ok: bool = False) -> FailureEvent:
    return FailureEvent.build(tool, ok, error)


class TestDenialV2:
    @pytest.mark.parametrize(
        "text",
        [
            "The tool call was denied by the user",
            "Claude requested PERMISSION TO USE Bash",
            "The user doesn't want to proceed with this tool use",
            "PreToolUse Hook Error: nope",
            "<tool_use_error>Blocked: not on the list",
            "This command requires approval",
        ],
    )
    def test_each_marker_counts(self, text: str) -> None:
        assert is_denial(text)

    @pytest.mark.parametrize(
        "text", ["! [rejected] main -> main (non-fast-forward)", "rg: not found", ""]
    )
    def test_rejected_and_plain_errors_do_not_count(self, text: str) -> None:
        assert not is_denial(text)

    def test_counted_per_errored_event_only(self, tmp_path: Path) -> None:
        records = [
            human("go"),
            *call(1, err="was denied"),
            *call(2, err="! [rejected] main"),
            *call(3),
        ]
        assert final(tmp_path, records, "denial_v2") == 1

    def test_successful_result_with_marker_text_not_counted(self) -> None:
        series = feat.event_feature_series([ev("was denied", ok=True)], [1])
        assert series[0]["denial_v2"] == 0


class TestFingerprint:
    def test_exit_code_line_skipped(self) -> None:
        got = feat.improved_fingerprint("Bash", "Exit code 1\nfatal: bad ref")
        assert got == failure_fingerprint("Bash", "fatal: bad ref")

    def test_exit_code_case_and_negative(self) -> None:
        got = feat.improved_fingerprint("Bash", "  EXIT CODE -1  \n\n  oops")
        assert got == failure_fingerprint("Bash", "oops")

    def test_no_next_line_keeps_exit_code(self) -> None:
        assert feat.improved_fingerprint("Bash", "Exit code 2") == failure_fingerprint(
            "Bash", "Exit code 2"
        )
        assert feat.improved_fingerprint("Bash", "Exit code 2\n  \n") == failure_fingerprint(
            "Bash", "Exit code 2"
        )

    def test_non_exit_code_first_line_unchanged(self) -> None:
        text = "Exit code 1 happened\nother"
        assert feat.improved_fingerprint("Bash", text) == failure_fingerprint("Bash", text)

    def test_blank_error_is_none(self) -> None:
        assert feat.improved_fingerprint("Bash", "  \n") is None

    def test_repeat_max_new_vs_old(self) -> None:
        events = [ev("Exit code 1\nalpha"), ev("Exit code 1\nbeta"), ev("Exit code 1\nalpha")]
        got = feat.event_feature_series(events, [3])[0]
        assert got["fp_repeat_max"] == 2
        assert got["fp_repeat_max_old"] == 3

    def test_repeat_sums_across_inputs_and_ignores_successes(self) -> None:
        events = [ev("boom", ok=True), ev("boom"), ev("boom")]
        assert feat.event_feature_series(events, [3])[0]["fp_repeat_max"] == 2

    def test_repeat_is_per_tool(self) -> None:
        events = [ev("boom", tool="Bash"), ev("boom", tool="Read")]
        assert feat.event_feature_series(events, [2])[0]["fp_repeat_max"] == 1


class TestErrorStreak:
    def test_longest_run(self) -> None:
        flags = [False, False, True, False, False, False, True]
        events = [ev("e", ok=ok) for ok in flags]
        assert feat.event_feature_series(events, [7])[0]["error_streak_max"] == 3

    def test_no_errors_zero(self) -> None:
        assert feat.event_feature_series([ev("", ok=True)], [1])[0]["error_streak_max"] == 0

    def test_empty_events(self) -> None:
        got = feat.event_feature_series([], [0, 0])
        assert got[0]["error_streak_max"] == 0 and len(got) == 2


class TestReplyRepeat:
    def test_near_duplicate_counts_and_first_stop_has_none(self, tmp_path: Path) -> None:
        records = [human("a"), prose(NEAR_A), human("b"), prose(NEAR_B), human("c")]
        got = [s["reply_repeat"] for s in stops_of(tmp_path, records)]
        assert got == [0, 1, 1]

    def test_dissimilar_does_not_count(self, tmp_path: Path) -> None:
        records = [human("a"), prose(NEAR_A), human("b"), prose(FAR)]
        assert final(tmp_path, records, "reply_repeat") == 0

    def test_threshold_both_sides(self) -> None:
        base = "a" * 100
        assert feat.near_duplicate(base, "a" * 85 + "b" * 15)  # ratio 0.85, at threshold
        assert feat.near_duplicate(base, "a" * 95 + "b" * 5)  # above
        assert not feat.near_duplicate(base, "a" * 84 + "b" * 16)  # ratio 0.84, below

    def test_case_and_whitespace_normalized(self) -> None:
        assert feat.near_duplicate("Hello   World\n", "hello world")

    def test_empty_never_matches(self) -> None:
        assert not feat.near_duplicate("", "")
        assert not feat.near_duplicate("   ", "text")

    def test_injected_prose_skipped(self, tmp_path: Path) -> None:
        reminder = "<system-reminder>" + NEAR_A
        records = [human("a"), prose(NEAR_A), human("b"), prose(reminder), prose(NEAR_B)]
        assert final(tmp_path, records, "reply_repeat") == 1
        only_injected = [human("a"), prose(reminder), human("b"), prose(reminder)]
        assert final(tmp_path, only_injected, "reply_repeat") == 0

    def test_final_block_of_turn_is_compared(self, tmp_path: Path) -> None:
        records = [human("a"), prose(NEAR_A), human("b"), prose(FAR), prose(NEAR_B)]
        assert final(tmp_path, records, "reply_repeat") == 1

    def test_non_text_blocks_and_user_text_ignored(self, tmp_path: Path) -> None:
        records = [
            human("a"),
            prose(NEAR_A, kind="thinking"),
            human("b"),
            prose(NEAR_A, kind="thinking"),
        ]
        assert final(tmp_path, records, "reply_repeat") == 0


class TestStopFeedback:
    FEEDBACK = "Stop hook feedback:\n[some hook]: keep going"

    def test_counts_prefixed_user_records(self, tmp_path: Path) -> None:
        records = [human("a"), human(self.FEEDBACK), human("  " + self.FEEDBACK), human("b")]
        assert final(tmp_path, records, "stop_feedback") == 2

    def test_other_text_not_counted(self, tmp_path: Path) -> None:
        records = [human("a"), human("please see Stop hook feedback: later"), human("b")]
        assert final(tmp_path, records, "stop_feedback") == 0

    def test_tool_results_not_counted(self, tmp_path: Path) -> None:
        records = [human("a"), *call(1, err=self.FEEDBACK)]
        assert final(tmp_path, records, "stop_feedback") == 0

    def test_sidechain_not_counted(self, tmp_path: Path) -> None:
        side = human(self.FEEDBACK)
        side["isSidechain"] = True
        assert final(tmp_path, [human("a"), side], "stop_feedback") == 0


class TestPrefixPerStop:
    def test_each_stop_sees_only_its_prefix(self, tmp_path: Path) -> None:
        records = [
            human("one"),
            *call(1, err="was denied"),
            prose(NEAR_A),
            human("two"),
            *call(2, err="was denied"),
            prose(NEAR_B),
            human("Stop hook feedback:\nx"),
            *call(3, err="was denied"),
        ]
        stops = stops_of(tmp_path, records)
        assert [s["denial_v2"] for s in stops] == [1, 2, 3]
        assert [s["fp_repeat_max"] for s in stops] == [1, 2, 3]
        assert [s["error_streak_max"] for s in stops] == [1, 2, 3]
        assert [s["reply_repeat"] for s in stops] == [0, 1, 1]
        assert [s["stop_feedback"] for s in stops] == [0, 0, 1]

    def test_counts_only_no_text_in_row(self, tmp_path: Path) -> None:
        stops = stops_of(tmp_path, [human("a"), prose(NEAR_A), human("b")])
        assert set(feat.FEATURE_KEYS) <= set(stops[0])
        assert all(isinstance(stops[0][k], int) for k in feat.FEATURE_KEYS)

    def test_session_without_events(self, tmp_path: Path) -> None:
        stops = stops_of(tmp_path, [human("only")])
        assert len(stops) == 1 and stops[0]["denial_v2"] == 0
