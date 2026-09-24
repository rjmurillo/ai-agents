"""Unit tests for `_codex_frames` (issue #5423 codex live-evidence work).

Deterministic cases over hand-built RUST_LOG-shaped strings. No subprocess,
no real codex CLI. `test_harness_capability_live_evidence.py` covers the
same module against the real checked-in trace captures; these tests pin the
parser's own contract in isolation.
"""

from __future__ import annotations

import pytest

from tests.eval._harness_capability_test_support import codex_frames as cf

MARKER = cf.FRAME_MARKER


def _line(payload: str, *, timestamp: str = "2026-09-24T12:00:00.000000Z") -> str:
    return f"{timestamp}{MARKER}{payload}"


def _created(response_id: str, model: str, effort: str, previous: str | None = None) -> str:
    prev = "null" if previous is None else f'"{previous}"'
    return _line(
        '{"type": "response.created", "response": {"id": "'
        + response_id
        + '", "model": "'
        + model
        + '", "previous_response_id": '
        + prev
        + ', "reasoning": {"effort": "'
        + effort
        + '"}}}'
    )


def _completed(response_id: str, model: str, effort: str, previous: str | None = None) -> str:
    prev = "null" if previous is None else f'"{previous}"'
    return _line(
        '{"type": "response.completed", "response": {"id": "'
        + response_id
        + '", "model": "'
        + model
        + '", "previous_response_id": '
        + prev
        + ', "reasoning": {"effort": "'
        + effort
        + '"}}}'
    )


def _spawn_agent(model: str | None, task_name: str) -> str:
    args = {"fork_turns": "none", "task_name": task_name}
    if model is not None:
        args["model"] = model
    import json

    arguments = json.dumps(args).replace('"', '\\"')
    return _line(
        '{"type": "response.output_item.done", "item": {"type": "function_call", '
        '"name": "spawn_agent", "arguments": "' + arguments + '"}}'
    )


def _message(text: str) -> str:
    return _line(
        '{"type": "response.output_item.done", "item": {"type": "message", '
        '"content": [{"type": "output_text", "text": "' + text + '"}]}}'
    )


# --- parse_codex_frames ---------------------------------------------------------


def test_non_marker_lines_are_ignored() -> None:
    stderr = "\n".join(
        [
            "2026-09-24T12:00:00.000000Z INFO some_module: unrelated startup line",
            "",
            _created("resp_1", "gpt-5.6-sol", "medium"),
            "2026-09-24T12:00:01.000000Z DEBUG other: also unrelated",
        ]
    )

    frames = cf.parse_codex_frames(stderr)

    assert len(frames) == 1
    assert frames[0].payload["type"] == "response.created"


def test_a_marker_line_carrying_binary_data_is_skipped_not_raised() -> None:
    """A live capture logs non-JSON websocket frames under the same marker.

    Quoted verbatim from `codex-0.156.0/thread-limit-1.trace.log` and
    `codex-0.156.0/concurrency-3-requested.trace.log`.
    """
    stderr = "\n".join(
        [
            _created("resp_1", "gpt-5.6-sol", "medium"),
            _line("Binary Data<length=4>"),
            _completed("resp_1", "gpt-5.6-sol", "medium"),
        ]
    )

    frames = cf.parse_codex_frames(stderr)

    assert len(frames) == 2
    assert [f.payload["type"] for f in frames] == ["response.created", "response.completed"]


def test_a_marker_line_carrying_raw_non_json_bytes_is_skipped_not_raised() -> None:
    """Quoted verbatim from `codex-0.156.0/thread-limit-1.trace.log`."""
    stderr = "\n".join([_created("resp_1", "gpt-5.6-sol", "medium"), _line("��?")])

    frames = cf.parse_codex_frames(stderr)

    assert len(frames) == 1


def test_a_marker_line_with_invalid_json_raises() -> None:
    """NEGATIVE CONTROL: a corrupt frame is a broken capture, not a negative result."""
    stderr = _line('{"type": "response.created", "response": {')

    with pytest.raises(cf.CodexFrameError, match="does not parse as JSON"):
        cf.parse_codex_frames(stderr)


def test_a_marker_line_with_a_json_array_is_skipped_not_raised() -> None:
    """A JSON value that is not an object never starts with `{`, so it is
    skipped by the same `startswith("{")` filter as the binary frames.
    """
    stderr = _line("[1, 2, 3]")

    assert cf.parse_codex_frames(stderr) == []


def test_parse_is_a_noop_on_empty_input() -> None:
    assert cf.parse_codex_frames("") == []


# --- response_spans --------------------------------------------------------------


def test_response_spans_pairs_created_and_completed_by_id() -> None:
    stderr = "\n".join(
        [
            _created("resp_1", "gpt-5.6-sol", "medium"),
            _completed("resp_1", "gpt-5.6-sol", "medium"),
            _created("resp_2", "gpt-6-luna", "high", previous=None),
        ]
    )

    spans = cf.response_spans(cf.parse_codex_frames(stderr))

    assert len(spans) == 2
    first, second = spans
    assert first.id == "resp_1"
    assert first.model == "gpt-5.6-sol"
    assert first.effort == "medium"
    assert first.created == 0
    assert first.completed == 1
    assert second.id == "resp_2"
    assert second.completed is None, "no completion frame arrived for resp_2"


def test_response_spans_opens_a_span_for_a_lone_completion() -> None:
    """A capture that starts mid-stream can show a completion with no prior creation."""
    stderr = _completed("resp_1", "gpt-5.6-sol", "medium")

    spans = cf.response_spans(cf.parse_codex_frames(stderr))

    assert len(spans) == 1
    assert spans[0].created == 0
    assert spans[0].completed == 0


def test_response_spans_ignores_frames_with_no_response_object() -> None:
    stderr = "\n".join([_spawn_agent("gpt-6-luna", "task_1"), _message("hello")])

    spans = cf.response_spans(cf.parse_codex_frames(stderr))

    assert spans == []


# --- function_calls / message_texts ----------------------------------------------


def test_function_calls_decodes_the_arguments_string() -> None:
    stderr = _spawn_agent("gpt-6-luna", "index_1")

    calls = cf.function_calls(cf.parse_codex_frames(stderr))

    assert calls == [
        ("spawn_agent", {"fork_turns": "none", "task_name": "index_1", "model": "gpt-6-luna"})
    ]


def test_function_calls_with_no_model_argument_carries_no_model_key() -> None:
    stderr = _spawn_agent(None, "reviewer_none")

    ((name, arguments),) = cf.function_calls(cf.parse_codex_frames(stderr))

    assert name == "spawn_agent"
    assert "model" not in arguments


def test_message_texts_collects_output_text_blocks_in_order() -> None:
    stderr = "\n".join([_message("1"), _message("2")])

    assert cf.message_texts(cf.parse_codex_frames(stderr)) == ["1", "2"]


# --- peak_overlap ------------------------------------------------------------------


def test_peak_overlap_counts_simultaneous_completed_spans() -> None:
    # Two children of the same model overlap: A opens, B opens, A closes, B closes.
    stderr = "\n".join(
        [
            _created("child_a", "gpt-6-luna", "high"),
            _created("child_b", "gpt-6-luna", "high"),
            _completed("child_a", "gpt-6-luna", "high"),
            _completed("child_b", "gpt-6-luna", "high"),
        ]
    )

    spans = cf.response_spans(cf.parse_codex_frames(stderr))

    assert cf.peak_overlap(spans, model="gpt-6-luna") == 2


def test_peak_overlap_is_one_for_strictly_sequential_children() -> None:
    stderr = "\n".join(
        [
            _created("child_a", "gpt-6-luna", "high"),
            _completed("child_a", "gpt-6-luna", "high"),
            _created("child_b", "gpt-6-luna", "high"),
            _completed("child_b", "gpt-6-luna", "high"),
        ]
    )

    spans = cf.response_spans(cf.parse_codex_frames(stderr))

    assert cf.peak_overlap(spans, model="gpt-6-luna") == 1


def test_peak_overlap_returns_none_with_no_completed_span_of_that_model() -> None:
    stderr = _created("child_a", "gpt-6-luna", "high")

    spans = cf.response_spans(cf.parse_codex_frames(stderr))

    assert cf.peak_overlap(spans, model="gpt-6-luna") is None


def test_peak_overlap_excludes_a_still_open_span_from_the_sweep() -> None:
    """NEGATIVE CONTROL: an unfinished child must not inflate or deflate the peak."""
    stderr = "\n".join(
        [
            _created("child_a", "gpt-6-luna", "high"),
            _completed("child_a", "gpt-6-luna", "high"),
            _created("child_b", "gpt-6-luna", "high"),  # never completes
        ]
    )

    spans = cf.response_spans(cf.parse_codex_frames(stderr))

    assert cf.peak_overlap(spans, model="gpt-6-luna") == 1


def test_peak_overlap_ignores_a_different_models_spans() -> None:
    stderr = "\n".join(
        [
            _created("parent", "gpt-5.6-sol", "medium"),
            _completed("parent", "gpt-5.6-sol", "medium"),
            _created("child", "gpt-6-luna", "high"),
            _completed("child", "gpt-6-luna", "high"),
        ]
    )

    spans = cf.response_spans(cf.parse_codex_frames(stderr))

    assert cf.peak_overlap(spans, model="gpt-6-luna") == 1
    assert cf.peak_overlap(spans, model="gpt-5.6-sol") == 1
    assert cf.peak_overlap(spans, model="gpt-5.6-terra") is None
