"""Tests for REQ-037: `_anthropic_response.classify_termination` and
`parse_message_response`.

Split out of `test_anthropic_stop_metadata.py` (taste-lints file-size gate);
see `_anthropic_stop_metadata_test_support.py` for the shared loader. Same-
shaped cases are tabled under one `@pytest.mark.parametrize` function each
(CQA cohesion gate: fewer `def`s per file), one behavior per table row.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.eval._anthropic_stop_metadata_test_support import _anthropic_response

# classify_termination

_CLASSIFY_ROWS: list[tuple[object, str, str]] = [
    ("end_turn", "completed", "end_turn_is_completed"),
    ("stop_sequence", "completed", "stop_sequence_is_completed"),
    ("refusal", "refusal", "refusal_is_refusal"),
    ("max_tokens", "token_limit", "max_tokens_is_token_limit"),
    ("model_context_window_exceeded", "token_limit", "context_window_is_token_limit"),
    ("tool_use", "incomplete", "tool_use_is_incomplete"),
    ("pause_turn", "incomplete", "pause_turn_is_incomplete"),
    ("some_future_reason", "incomplete", "unrecognized_string_is_incomplete"),
    (None, "unknown", "missing_is_unknown"),
    (42, "unknown", "int_is_unknown"),
    (3.14, "unknown", "float_is_unknown"),
    (["end_turn"], "unknown", "list_is_unknown"),
    ({"reason": "end_turn"}, "unknown", "dict_is_unknown"),
    (True, "unknown", "bool_is_unknown"),
]
_CLASSIFY_CASES = [(stop_reason, expected) for stop_reason, expected, _id in _CLASSIFY_ROWS]
_CLASSIFY_IDS = [row_id for _sr, _exp, row_id in _CLASSIFY_ROWS]


@pytest.mark.parametrize("stop_reason, expected", _CLASSIFY_CASES, ids=_CLASSIFY_IDS)
def test_classify_termination(stop_reason: object, expected: str) -> None:
    assert _anthropic_response.classify_termination(stop_reason) == expected


# parse_message_response

_UNKNOWN_STOP_REASON = {"termination": "unknown", "stop_reason": None}
_REFUSED_NO_DETAILS = {
    "termination": "refusal", "refusal_category": None, "refusal_explanation": None
}
# REQ-037 Failure Modes: an unrecognized stop reason must not be scored as a
# completed answer, same as a refusal or a token_limit.
_INCOMPLETE_BLOCKS = {"termination": "incomplete", "blocks_scoring": True}
_THINKING_BLOCK = {"type": "thinking", "thinking": "reasoning..."}

# (payload, expected, id) rows. A plain tuple list plus a separate `ids=`
# list (below) avoids one `pytest.param(...)` wrapper per row: CQA
# non-redundancy flags the repeated wrapper/closer lines a table this size
# produces otherwise.
_HELLO_TEXT = {"content": [{"type": "text", "text": "hello"}], "stop_reason": "end_turn"}
_COMPLETED_HELLO = {
    "termination": "completed",
    "text": "hello",
    "stop_reason": "end_turn",
    "block_types": ("text",),
    "blocks_scoring": False,
}
_REFUSAL_DETAILS_PAYLOAD = {
    "content": [],
    "stop_reason": "refusal",
    "stop_details": {"category": "policy", "explanation": "declined"},
}
_REFUSED_WITH_DETAILS = {
    "termination": "refusal",
    "refusal_category": "policy",
    "refusal_explanation": "declined",
    "blocks_scoring": True,
}
_TEXT_FIRST = {"type": "text", "text": "first"}
_TEXT_SECOND = {"type": "text", "text": "second"}
_MIXED_BLOCKS_PAYLOAD = {
    "content": [_THINKING_BLOCK, _TEXT_FIRST, _TEXT_SECOND],
    "stop_reason": "end_turn",
}

_PARSE_ROWS: list[tuple[dict[str, Any], dict[str, Any], str]] = [
    (_HELLO_TEXT, _COMPLETED_HELLO, "end_turn_returns_completed_and_text"),
    (_REFUSAL_DETAILS_PAYLOAD, _REFUSED_WITH_DETAILS, "refusal_with_stop_details_reads_category"),
    (
        {"content": [], "stop_reason": "refusal", "stop_details": None},
        _REFUSED_NO_DETAILS,
        "refusal_with_null_stop_details_has_no_refusal_fields",
    ),
    (
        {"content": [], "stop_reason": "refusal"},
        _REFUSED_NO_DETAILS,
        "refusal_missing_stop_details",
    ),
    (
        {
            "content": [],
            "stop_reason": "refusal",
            "stop_details": {"category": 1, "explanation": None},
        },
        {"refusal_category": None, "refusal_explanation": None},
        "refusal_stop_details_with_non_string_fields_are_dropped",
    ),
    (
        {"content": [{"type": "text", "text": "cut off"}], "stop_reason": "max_tokens"},
        {"termination": "token_limit", "blocks_scoring": True},
        "max_tokens_stop_reason_is_token_limit",
    ),
    (
        {"content": [_THINKING_BLOCK], "stop_reason": "max_tokens"},
        {"text": "", "termination": "token_limit", "block_types": ("thinking",)},
        "max_tokens_with_only_thinking_blocks_has_empty_text",
    ),
    (
        _MIXED_BLOCKS_PAYLOAD,
        {"block_types": ("thinking", "text", "text"), "text": "first\nsecond"},
        "mixed_thinking_and_text_blocks_preserve_order_and_join_text_only",
    ),
    *[
        ({"content": [], "stop_reason": reason}, _INCOMPLETE_BLOCKS, f"unrecognized_{reason}")
        for reason in ("tool_use", "pause_turn", "weird_new_reason")
    ],
    ({"content": []}, _UNKNOWN_STOP_REASON, "missing_stop_reason_is_unknown"),
    ({"content": [], "stop_reason": 42}, _UNKNOWN_STOP_REASON, "non_string_stop_reason_is_unknown"),
    (
        {"content": ["not-a-block", {"type": "text", "text": "kept"}], "stop_reason": "end_turn"},
        {"block_types": ("text",), "text": "kept"},
        "non_dict_content_blocks_are_skipped",
    ),
]
_PARSE_CASES = [(payload, expected) for payload, expected, _id in _PARSE_ROWS]
_PARSE_IDS = [row_id for _payload, _expected, row_id in _PARSE_ROWS]


@pytest.mark.parametrize("payload, expected", _PARSE_CASES, ids=_PARSE_IDS)
def test_parse_message_response(payload: dict[str, Any], expected: dict[str, Any]) -> None:
    response = _anthropic_response.parse_message_response(payload)
    for attr, value in expected.items():
        assert getattr(response, attr) == value, attr
