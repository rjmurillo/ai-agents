"""Tests for REQ-037: `_anthropic_response.classify_termination` and
`parse_message_response`.

Split out of `test_anthropic_stop_metadata.py` (taste-lints file-size gate);
see `_anthropic_stop_metadata_test_support.py` for the shared loader.
"""

from __future__ import annotations

import pytest

from tests.eval._anthropic_stop_metadata_test_support import _anthropic_response

# ---------------------------------------------------------------------------
# classify_termination
# ---------------------------------------------------------------------------


class TestClassifyTermination:
    @pytest.mark.parametrize("stop_reason", ["end_turn", "stop_sequence"])
    def test_completed_stop_reasons(self, stop_reason: str) -> None:
        assert _anthropic_response.classify_termination(stop_reason) == "completed"

    def test_refusal(self) -> None:
        assert _anthropic_response.classify_termination("refusal") == "refusal"

    @pytest.mark.parametrize("stop_reason", ["max_tokens", "model_context_window_exceeded"])
    def test_token_limit_stop_reasons(self, stop_reason: str) -> None:
        assert _anthropic_response.classify_termination(stop_reason) == "token_limit"

    @pytest.mark.parametrize("stop_reason", ["tool_use", "pause_turn", "some_future_reason"])
    def test_unrecognized_string_is_incomplete(self, stop_reason: str) -> None:
        assert _anthropic_response.classify_termination(stop_reason) == "incomplete"

    def test_missing_stop_reason_is_unknown(self) -> None:
        assert _anthropic_response.classify_termination(None) == "unknown"

    @pytest.mark.parametrize("stop_reason", [42, 3.14, ["end_turn"], {"reason": "end_turn"}, True])
    def test_non_string_stop_reason_is_unknown(self, stop_reason: object) -> None:
        assert _anthropic_response.classify_termination(stop_reason) == "unknown"


# ---------------------------------------------------------------------------
# parse_message_response
# ---------------------------------------------------------------------------


class TestParseMessageResponse:
    def test_end_turn_returns_completed_and_text(self) -> None:
        response = _anthropic_response.parse_message_response(
            {"content": [{"type": "text", "text": "hello"}], "stop_reason": "end_turn"}
        )
        assert response.termination == "completed"
        assert response.text == "hello"
        assert response.stop_reason == "end_turn"
        assert response.block_types == ("text",)
        assert response.blocks_scoring is False

    def test_refusal_with_stop_details_reads_category_and_explanation(self) -> None:
        response = _anthropic_response.parse_message_response(
            {
                "content": [],
                "stop_reason": "refusal",
                "stop_details": {"category": "policy", "explanation": "declined"},
            }
        )
        assert response.termination == "refusal"
        assert response.refusal_category == "policy"
        assert response.refusal_explanation == "declined"
        assert response.blocks_scoring is True

    def test_refusal_with_null_stop_details_has_no_refusal_fields(self) -> None:
        response = _anthropic_response.parse_message_response(
            {"content": [], "stop_reason": "refusal", "stop_details": None}
        )
        assert response.termination == "refusal"
        assert response.refusal_category is None
        assert response.refusal_explanation is None

    def test_refusal_with_missing_stop_details_key_has_no_refusal_fields(self) -> None:
        response = _anthropic_response.parse_message_response(
            {"content": [], "stop_reason": "refusal"}
        )
        assert response.termination == "refusal"
        assert response.refusal_category is None
        assert response.refusal_explanation is None

    def test_refusal_stop_details_with_non_string_fields_are_dropped(self) -> None:
        response = _anthropic_response.parse_message_response(
            {
                "content": [],
                "stop_reason": "refusal",
                "stop_details": {"category": 1, "explanation": None},
            }
        )
        assert response.refusal_category is None
        assert response.refusal_explanation is None

    def test_max_tokens_stop_reason_is_token_limit(self) -> None:
        response = _anthropic_response.parse_message_response(
            {"content": [{"type": "text", "text": "cut off"}], "stop_reason": "max_tokens"}
        )
        assert response.termination == "token_limit"
        assert response.blocks_scoring is True

    def test_max_tokens_with_only_thinking_blocks_has_empty_text(self) -> None:
        response = _anthropic_response.parse_message_response(
            {
                "content": [{"type": "thinking", "thinking": "reasoning..."}],
                "stop_reason": "max_tokens",
            }
        )
        assert response.text == ""
        assert response.termination == "token_limit"
        assert response.block_types == ("thinking",)

    def test_mixed_thinking_and_text_blocks_preserve_order_and_join_text_only(self) -> None:
        response = _anthropic_response.parse_message_response(
            {
                "content": [
                    {"type": "thinking", "thinking": "reasoning..."},
                    {"type": "text", "text": "first"},
                    {"type": "text", "text": "second"},
                ],
                "stop_reason": "end_turn",
            }
        )
        assert response.block_types == ("thinking", "text", "text")
        assert response.text == "first\nsecond"

    @pytest.mark.parametrize("stop_reason", ["tool_use", "pause_turn", "weird_new_reason"])
    def test_unrecognized_stop_reason_is_incomplete(self, stop_reason: str) -> None:
        response = _anthropic_response.parse_message_response(
            {"content": [], "stop_reason": stop_reason}
        )
        assert response.termination == "incomplete"
        # REQ-037 Failure Modes: an unrecognized stop reason must not be
        # scored as a completed answer, same as a refusal or a token_limit.
        assert response.blocks_scoring is True

    def test_missing_stop_reason_is_unknown(self) -> None:
        response = _anthropic_response.parse_message_response({"content": []})
        assert response.termination == "unknown"
        assert response.stop_reason is None

    def test_non_string_stop_reason_is_unknown(self) -> None:
        response = _anthropic_response.parse_message_response(
            {"content": [], "stop_reason": 42}
        )
        assert response.termination == "unknown"
        assert response.stop_reason is None

    def test_non_dict_content_blocks_are_skipped(self) -> None:
        response = _anthropic_response.parse_message_response(
            {
                "content": ["not-a-block", {"type": "text", "text": "kept"}],
                "stop_reason": "end_turn",
            }
        )
        assert response.block_types == ("text",)
        assert response.text == "kept"
