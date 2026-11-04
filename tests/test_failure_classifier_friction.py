"""Tests for the REQ-048 TASK-001 friction v2 signals: error_streak and friction_score."""

from __future__ import annotations

import pytest

from scripts.failure_classifier import (
    DENIAL_MARKERS,
    FRICTION_TIER1_DEFAULT,
    FRICTION_WEIGHTS,
    FailureEvent,
    classify,
    friction_score,
)

TEST = "pytest tests/a.py"


def ev(
    tool: str,
    ok: bool,
    error: str = "",
    cmd: str | None = None,
    target: str | None = None,
    check: bool | None = None,
):
    return FailureEvent.build(tool=tool, ok=ok, error=error, input=cmd, target=target, check=check)


class TestDenialMarkers:
    def test_marker_set_is_the_frozen_friction_v2_set(self) -> None:
        assert DENIAL_MARKERS == (
            "was denied",
            "permission to use",
            "user doesn't want to proceed",
            "hook error",
            "<tool_use_error>blocked",
            "requires approval",
            "permission denied because no interactive user response",
            "rejected by user approval settings",
        )

    @pytest.mark.parametrize("marker", DENIAL_MARKERS)
    def test_text_without_the_marker_is_a_tool_error(self, marker: str) -> None:
        signals = classify([ev("Bash", False, marker[:-1])])
        assert (signals.permission_denial, signals.tool_error) == (0, 1)

    @pytest.mark.parametrize(
        "error", ["Permission denied", "! [rejected] main -> main", "rejected"]
    )
    def test_removed_markers_are_tool_errors(self, error: str) -> None:
        signals = classify([ev("Bash", False, error)])
        assert (signals.permission_denial, signals.tool_error) == (0, 1)


class TestHarnessDenialWordings:
    @pytest.mark.parametrize(
        "error",
        [
            "Permission denied because no interactive user response was available",
            "command rejected by user approval settings",
        ],
    )
    def test_copilot_and_codex_wordings_are_denials(self, error: str) -> None:
        signals = classify([ev("Bash", False, error)])
        assert (signals.permission_denial, signals.tool_error) == (1, 0)

    @pytest.mark.parametrize(
        "error",
        [
            "bash: ./run.sh: Permission denied",
            "Permission denied because the file is read-only",
            "rejected by the remote",
            "rejected by user",
        ],
    )
    def test_unix_eacces_and_partial_wordings_stay_tool_errors(self, error: str) -> None:
        signals = classify([ev("Bash", False, error)])
        assert (signals.permission_denial, signals.tool_error) == (0, 1)


class TestErrorStreak:
    def test_empty_input_is_zero(self) -> None:
        assert classify([]).error_streak == 0

    def test_all_ok_is_zero(self) -> None:
        assert classify([ev("Bash", True)] * 4).error_streak == 0

    def test_interleaved_takes_the_longest_run(self) -> None:
        ok, bad = ev("Bash", True), ev("Bash", False, "boom")
        assert classify([bad, bad, ok, bad, bad, bad, ok, bad]).error_streak == 3

    def test_unfingerprinted_errors_extend_a_run(self) -> None:
        bad, blank = ev("Bash", False, "boom"), ev("Bash", False, "")
        signals = classify([bad, blank, bad])
        assert (signals.error_streak, signals.unfingerprinted) == (3, 1)

    def test_run_ending_the_sequence_counts(self) -> None:
        assert classify([ev("Bash", True)] + [ev("Bash", False, "x")] * 2).error_streak == 2


class TestFrictionScore:
    def test_weights_and_default_are_the_frozen_config(self) -> None:
        assert dict(FRICTION_WEIGHTS) == {
            "tool_error": 0,
            "permission_denial": 2,
            "failed_retry": 0,
            "edit_churn": 0,
            "stop_feedback": 2,
            "error_streak": 1,
        }
        assert FRICTION_TIER1_DEFAULT == 10

    def test_empty_signals_score_zero(self) -> None:
        assert friction_score(classify([]), 0) == 0

    def test_hand_computed_total(self) -> None:
        # 2 denials (2 each = 4), 3 errors in a row (streak 3 = 3), the
        # 3 tool errors and the failed retries weigh 0, 2 feedback (2 each = 4).
        denied = ev("Bash", False, "was denied")
        boom = ev("Bash", False, "boom")
        events = [denied, denied, boom]
        signals = classify(events)
        assert (signals.permission_denial, signals.tool_error) == (2, 1)
        assert signals.error_streak == 3
        assert friction_score(signals, 2) == 4 + 3 + 4

    def test_stop_feedback_alone(self) -> None:
        assert friction_score(classify([]), 3) == 6

    def test_zero_weight_signals_do_not_score(self) -> None:
        boom = ev("Bash", False, "boom", TEST)
        ok = ev("Bash", True)
        signals = classify([boom, ok, boom, ok, boom])
        assert (signals.tool_error, signals.failed_retry) == (3, 2)
        assert friction_score(signals, 0) == 1  # streak 1 only

    def test_edit_churn_counts_targets_but_weighs_zero(self) -> None:
        cycle = [ev("Edit", True, target="a.py"), ev("Bash", False, "E1", TEST, check=True)]
        signals = classify(cycle * 3)
        assert len(signals.churned_targets(3)) == 1
        assert len(signals.churned_targets(4)) == 0
        assert friction_score(signals, 0) == friction_score(signals, 0, churn_threshold=4) == 1
