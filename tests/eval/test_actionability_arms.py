"""Tests for the pure arm, parser, and prompt code in scripts/eval/actionability_arms.py.

Plan M1-T13 and M1-T14. Shared helpers: _actionability_arms_test_support.py.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._actionability_arms_test_support import aa, make_prediction, make_row

_SCRIPT = Path(aa.__file__)


def _prediction(**kwargs: Any) -> Any:
    return aa.Prediction.from_dict(make_prediction("X", **kwargs))


class TestArmsAAndB:
    @pytest.mark.parametrize(
        ("score", "expected"),
        [(0.5, True), (0.51, True), (0.49, False), (0.0, False), (1.0, True)],
    )
    def test_arm_a_treats_the_tie_as_actionable(self, score: float, expected: bool) -> None:
        """Plan M1-T13: arm A is the heuristic as shipped, `>= 0.5`."""
        assert aa.arm_a(make_row("r", score=score)) is expected

    @pytest.mark.parametrize(
        ("score", "expected"),
        [(0.5, False), (0.51, True), (0.49, False), (0.0, False), (1.0, True)],
    )
    def test_arm_b_breaks_the_tie_the_other_way(self, score: float, expected: bool) -> None:
        """Plan M1-T13: arm B is the heuristic with `> 0.5`."""
        assert aa.arm_b(make_row("r", score=score)) is expected

    def test_arms_a_and_b_disagree_only_at_exactly_one_half(self) -> None:
        """Plan M1-T13: the 0.5 boundary is the only place A and B differ."""
        scores = [0.0, 0.3, 0.49, 0.5, 0.51, 0.7, 1.0]

        differing = [
            s
            for s in scores
            if aa.arm_a(make_row("r", score=s)) != aa.arm_b(make_row("r", score=s))
        ]

        assert differing == [0.5]


class TestArmC:
    def test_confident_ok_prediction_in_band_overrides_the_heuristic(self) -> None:
        """Plan M1-T14: in band, ok, confidence >= 0.7 means the model verdict applies."""
        row = make_row("r", score=0.5)

        assert aa.arm_a(row) is True
        assert aa.arm_c(row, _prediction(is_actionable=False, confidence=0.7)) is False

    def test_confidence_just_under_the_threshold_keeps_the_heuristic(self) -> None:
        """Plan M1-T14: 0.69 is under the 0.7 apply rule."""
        row = make_row("r", score=0.5)

        assert aa.arm_c(row, _prediction(is_actionable=False, confidence=0.69)) is True

    def test_out_of_band_row_ignores_the_prediction(self) -> None:
        """Plan M1-T14: production only calls the model inside the band."""
        row = make_row("r", score=0.9, in_band=False)

        assert aa.arm_c(row, _prediction(is_actionable=False, confidence=0.99)) is True

    def test_missing_prediction_falls_back_to_arm_a(self) -> None:
        """Plan M1-T14: no prediction record means the heuristic verdict."""
        assert aa.arm_c(make_row("r", score=0.5), None) is True
        assert aa.arm_c(make_row("r", score=0.2), None) is False

    @pytest.mark.parametrize("status", ["parse_error", "call_error"])
    def test_failed_prediction_falls_back_to_arm_a(self, status: str) -> None:
        """Plan M1-T14: a failed call keeps the heuristic verdict."""
        row = make_row("r", score=0.5)
        prediction = _prediction(status=status, is_actionable=None, confidence=None)

        assert aa.arm_c(row, prediction) is True

    def test_ok_status_without_a_verdict_falls_back_to_arm_a(self) -> None:
        """Plan M1-T14: a malformed ok record cannot apply a verdict it does not hold."""
        row = make_row("r", score=0.5)

        assert aa.arm_c(row, _prediction(is_actionable=None, confidence=0.99)) is True
        assert aa.arm_c(row, _prediction(is_actionable=False, confidence=None)) is True


class TestNoRescoring:
    def test_arms_never_call_the_heuristic_scorer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Plan M1-T13, premortem R1: arms read the stored score, never rescore."""

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("get_actionability_score was called")

        import scripts.update_reviewer_signal_stats as stats

        monkeypatch.setattr(stats, "get_actionability_score", _boom)
        monkeypatch.setattr(aa, "get_actionability_score", _boom, raising=False)
        row = make_row("r", score=0.5)

        assert aa.arm_a(row) is True
        assert aa.arm_b(row) is False
        assert aa.arm_c(row, _prediction()) is True

    def test_module_source_does_not_reference_the_scorer(self) -> None:
        """Plan M1-T13, premortem R1: a structural guard on top of the behavioral one."""
        assert "get_actionability_score" not in _SCRIPT.read_text(encoding="utf-8")


class TestPredictionFromDict:
    def test_reads_every_field(self) -> None:
        """Plan M1-T14: a record round-trips into a Prediction."""
        prediction = aa.Prediction.from_dict(make_prediction("Z", confidence=0.8))

        assert prediction.id == "Z"
        assert prediction.status == "ok"
        assert prediction.is_actionable is True
        assert prediction.confidence == 0.8
        assert prediction.latency_s == 0.25

    def test_missing_optional_fields_become_none(self) -> None:
        """Plan M1-T14: call_error records carry no verdict."""
        prediction = aa.Prediction.from_dict({"id": "Z", "status": "call_error"})

        assert prediction.is_actionable is None
        assert prediction.confidence is None
        assert prediction.latency_s is None


class TestParseVerdict:
    def test_valid_object_parses(self) -> None:
        """Plan M1-T14: the happy path."""
        verdict = aa.parse_verdict('{"is_actionable": true, "confidence": 0.82, "reason": "x"}')

        assert verdict == aa.Verdict(is_actionable=True, confidence=0.82, reason="x")

    def test_false_is_a_real_verdict(self) -> None:
        """Plan M1-T14: False is a value, not a parse failure."""
        verdict = aa.parse_verdict('{"is_actionable": false, "confidence": 0.9}')

        assert verdict is not None
        assert verdict.is_actionable is False
        assert verdict.reason == ""

    def test_json_fence_is_tolerated(self) -> None:
        """Plan M1-T14: one surrounding ```json fence is accepted."""
        text = '```json\n{"is_actionable": true, "confidence": 0.8}\n```'

        assert aa.parse_verdict(text) is not None

    def test_bare_fence_is_tolerated(self) -> None:
        """Plan M1-T14: a fence with no language tag is accepted."""
        text = '```\n{"is_actionable": true, "confidence": 0.8}\n```'

        assert aa.parse_verdict(text) is not None

    def test_surrounding_whitespace_is_tolerated(self) -> None:
        """Plan M1-T14: leading and trailing whitespace is not a defect."""
        assert aa.parse_verdict('\n  {"is_actionable": true, "confidence": 1}  \n') is not None

    @pytest.mark.parametrize(
        ("confidence", "expected"), [(1.5, 1.0), (-2, 0.0), (0, 0.0), (1, 1.0), (0.4, 0.4)]
    )
    def test_confidence_is_clamped_to_the_unit_interval(
        self, confidence: float, expected: float
    ) -> None:
        """Plan M1-T14: confidence clamps to [0, 1]."""
        text = json.dumps({"is_actionable": True, "confidence": confidence})

        verdict = aa.parse_verdict(text)

        assert verdict is not None
        assert verdict.confidence == expected

    def test_reason_is_truncated_to_100_characters(self) -> None:
        """Plan M1-T14: reason truncates at 100."""
        text = json.dumps({"is_actionable": True, "confidence": 1, "reason": "r" * 250})

        verdict = aa.parse_verdict(text)

        assert verdict is not None
        assert verdict.reason == "r" * 100

    def test_non_string_reason_becomes_empty(self) -> None:
        """Plan M1-T14: reason is not part of the verdict, so a bad one is dropped, not fatal."""
        verdict = aa.parse_verdict('{"is_actionable": true, "confidence": 1, "reason": 5}')

        assert verdict is not None
        assert verdict.reason == ""

    @pytest.mark.parametrize(
        "text",
        [
            '{"is_actionable": 1, "confidence": 0.9}',
            '{"is_actionable": 0, "confidence": 0.9}',
            '{"is_actionable": "true", "confidence": 0.9}',
            '{"is_actionable": null, "confidence": 0.9}',
        ],
        ids=["int-one", "int-zero", "string", "null"],
    )
    def test_is_actionable_must_be_a_real_bool(self, text: str) -> None:
        """Plan M1-T14: a non-bool is_actionable is a parse failure, never False."""
        assert aa.parse_verdict(text) is None

    def test_missing_is_actionable_is_rejected(self) -> None:
        """Plan M1-T14: missing is_actionable is a parse failure."""
        assert aa.parse_verdict('{"confidence": 0.9}') is None

    def test_missing_confidence_is_rejected(self) -> None:
        """Plan M1-T14: missing confidence is a parse failure."""
        assert aa.parse_verdict('{"is_actionable": true}') is None

    def test_string_confidence_is_rejected(self) -> None:
        """Plan M1-T14: a string confidence is a parse failure."""
        assert aa.parse_verdict('{"is_actionable": true, "confidence": "0.9"}') is None

    def test_bool_confidence_is_rejected(self) -> None:
        """Plan M1-T14: True is an int in Python but not a confidence."""
        assert aa.parse_verdict('{"is_actionable": true, "confidence": true}') is None

    @pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e999"])
    def test_non_finite_confidence_is_rejected(self, literal: str) -> None:
        """Plan M1-T14: NaN compares False to 0.7, so it must never become a verdict."""
        text = '{"is_actionable": true, "confidence": ' + literal + "}"

        assert aa.parse_verdict(text) is None

    @pytest.mark.parametrize(
        "text",
        ["", "   ", "not json", "[1, 2]", '"a string"', "42", "null", "{broken"],
        ids=["empty", "blank", "prose", "list", "string", "number", "null", "truncated"],
    )
    def test_non_object_or_invalid_json_is_rejected(self, text: str) -> None:
        """Plan M1-T14: only a JSON object can be a verdict."""
        assert aa.parse_verdict(text) is None

    def test_prose_around_the_object_is_rejected(self) -> None:
        """Plan M1-T14: the prompt says reply with only the object, so prose is a failure."""
        text = 'Sure! {"is_actionable": true, "confidence": 0.9}'

        assert aa.parse_verdict(text) is None

    def test_doubly_fenced_text_is_rejected(self) -> None:
        """Plan M1-T14: only one surrounding fence is tolerated."""
        text = '```json\n```json\n{"is_actionable": true, "confidence": 0.9}\n```\n```'

        assert aa.parse_verdict(text) is None


class TestPrompt:
    def test_system_prompt_demands_only_the_json_object(self) -> None:
        """Plan M1-T14: prompt-v1.md tells the model to reply with only the JSON object."""
        system, _ = aa.load_prompt()

        assert "ONLY" in system
        assert "is_actionable" in system
        assert "confidence" in system

    def test_prompt_hash_is_sha256_of_the_file_bytes(self) -> None:
        """Plan M1-T14: the recorded hash identifies the exact prompt file."""
        _, digest = aa.load_prompt()

        assert digest == hashlib.sha256(aa.PROMPT_PATH.read_bytes()).hexdigest()

    def test_user_message_carries_body_and_path(self) -> None:
        """Plan M1-T14: the model sees the comment and the file path."""
        row = make_row("r", body="Please add a null check", path="src/x.py")

        message = aa.build_user_message(row)

        assert "Please add a null check" in message
        assert "src/x.py" in message

    def test_user_message_never_carries_the_heuristic_score(self) -> None:
        """Plan M1-T14 and spec Call contract: the score is logged, not sent."""
        row = make_row("r", score=0.5123, heuristic_reasons=["matched-pattern"])

        message = aa.build_user_message(row)

        assert "0.5123" not in message
        assert "matched-pattern" not in message
        assert "heuristic" not in message.lower()

    def test_user_message_truncates_body_to_4000_characters(self) -> None:
        """Plan M1-T14 and spec Call contract: body truncates at 4000."""
        message = aa.build_user_message(make_row("r", body="b" * 5000))

        assert "b" * 4000 in message
        assert "b" * 4001 not in message

    def test_user_message_keeps_three_replies_each_truncated_to_500(self) -> None:
        """Plan M1-T14 and spec Call contract: up to 3 replies, 500 characters each."""
        replies = ["a" * 600, "b" * 600, "c" * 600, "d" * 600]

        message = aa.build_user_message(make_row("r", thread_replies=replies))

        assert "a" * 500 in message
        assert "a" * 501 not in message
        assert "c" * 500 in message
        assert "d" * 10 not in message

    def test_user_message_without_replies_has_no_reply_block(self) -> None:
        """Plan M1-T14: no replies means no reply tags."""
        assert "<reply>" not in aa.build_user_message(make_row("r"))


class TestCleanConfidenceOverflow:
    def test_integer_too_large_for_a_float_is_rejected(self) -> None:
        """Hygiene 6d: float(10**400) raises OverflowError, which must become a parse failure."""
        text = '{"is_actionable": true, "confidence": 1' + "0" * 400 + "}"

        assert aa.parse_verdict(text) is None
