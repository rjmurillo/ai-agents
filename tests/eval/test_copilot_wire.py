"""Unit tests for `_copilot_wire` (issue #5423 BYOK scope addition, reopen).

Deterministic cases over hand-built `[rust:model_wire]` log text, matching
the real multi-line shape a live capture produces: only a body's first
physical line carries the timestamp and marker prefix, every continuation
line is the bare JSON fragment, and unrelated `[rust:...]` lines can appear
between a `response (Request-ID ...)` header and the body that pairs with
it. No subprocess, no real Copilot CLI.
`test_harness_capability_live_evidence_copilot.py` covers the same module
against the real checked-in `copilot-1.0.89-byok-anthropic/*.wire.log`
captures; these tests pin the parser's own contract in isolation.
"""

from __future__ import annotations

import pytest

from tests.eval._harness_capability_test_support import copilot_wire as cw

#: The literal text every `[rust:model_wire]` log line's first physical line
#: carries, quoted verbatim from
#: `copilot-1.0.89-byok-anthropic/child-model-override.wire.log`.
MARKER = "[rust:model_wire] "


def _line(text: str, *, ts: str = "2026-09-24T12:53:39.142Z") -> str:
    """One marker line: a timestamp, `[DEBUG]`, the marker, then `text`."""
    return f"{ts} [DEBUG] {MARKER}{text}"


def _other(text: str, *, ts: str = "2026-09-24T12:54:06.587Z") -> str:
    """An unrelated `[rust:...]` log line: a real line, but not model_wire."""
    return f"{ts} [DEBUG] [rust:copilot_runtime::session::pending_request_flow] {text}"


def _request_block(model: str, budget: int | None) -> list[str]:
    thinking = f'"thinking": {{"budget_tokens": {budget}}}, ' if budget is not None else ""
    return [
        _line("Wire request: {"),
        f'  "model": "{model}",',
        f"  {thinking}" if thinking else "",
        '  "stream": true',
        "}",
    ]


def _response_header(request_id: str) -> str:
    return _line(f"response (Request-ID {request_id}):")


def _response_body(response_id: str, model: str) -> list[str]:
    return [
        _line("{"),
        f'  "id": "{response_id}",',
        f'  "model": "{model}",',
        '  "usage": {"prompt_tokens": 1}',
        "}",
    ]


# --- parse_wire_requests -----------------------------------------------------------


def test_parse_wire_requests_reads_model_and_budget_from_a_multi_line_body() -> None:
    text = "\n".join(_request_block("claude-haiku-4-5", 1024))

    requests = cw.parse_wire_requests(text)

    assert requests == [cw.WireRequest(model="claude-haiku-4-5", thinking_budget_tokens=1024)]


def test_parse_wire_requests_allows_a_missing_thinking_block() -> None:
    text = "\n".join(
        [_line("Wire request: {"), '  "model": "claude-haiku-4-5",', '  "stream": true', "}"]
    )

    requests = cw.parse_wire_requests(text)

    assert requests == [cw.WireRequest(model="claude-haiku-4-5", thinking_budget_tokens=None)]


def test_a_single_line_request_body_still_parses() -> None:
    text = _line('Wire request: {"model": "claude-haiku-4-5", "stream": true}')

    requests = cw.parse_wire_requests(text)

    assert requests == [cw.WireRequest(model="claude-haiku-4-5", thinking_budget_tokens=None)]


def test_lines_without_the_model_wire_marker_are_ignored() -> None:
    text = "\n".join([_other("noise"), *_request_block("claude-haiku-4-5", 1024)])

    assert len(cw.parse_wire_requests(text)) == 1


# --- parse_wire_responses -----------------------------------------------------------


def test_parse_wire_responses_pairs_a_multi_line_body_with_its_header() -> None:
    text = "\n".join(
        [
            _response_header("req_1"),
            _line("data:"),
            *_response_body("msg_1", "claude-haiku-4-5-20251001"),
        ]
    )

    responses = cw.parse_wire_responses(text)

    assert len(responses) == 1
    assert responses[0].request_id == "req_1"
    assert responses[0].id == "msg_1"
    assert responses[0].model == "claude-haiku-4-5-20251001"
    assert responses[0].usage == {"prompt_tokens": 1}


def test_parse_wire_responses_reads_several_blocks_in_order() -> None:
    text = "\n".join(
        [
            _response_header("req_1"),
            _line("data:"),
            *_response_body("msg_1", "claude-haiku-4-5-20251001"),
            _response_header("req_2"),
            _line("data:"),
            *_response_body("msg_2", "claude-sonnet-4-6"),
        ]
    )

    responses = cw.parse_wire_responses(text)

    assert [r.model for r in responses] == ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]


def test_unrelated_log_lines_between_a_header_and_its_body_do_not_break_pairing() -> None:
    """The exact shape that silently lost 2 of 6 responses before this fix.

    Quoted verbatim from
    `copilot-1.0.89-byok-anthropic/concurrency-3-requested.wire.log`: a
    `response (Request-ID ...)` header, then several
    `[rust:copilot_runtime::...]` lines (a different marker entirely,
    interleaved with the `data:` line), before the body's own
    `[rust:model_wire] {` line.
    """
    text = "\n".join(
        [
            _response_header("req_011CfNJEiGFRy14RyAtxdZUh"),
            _other("Detached host delivery retirement decision completed"),
            _line("data:"),
            _other("Detached host delivery started"),
            _other("Detached host delivery completed"),
            *_response_body("msg_011CfNJEia7VkdqDg9rxsVPV", "claude-haiku-4-5-20251001"),
        ]
    )

    responses = cw.parse_wire_responses(text)

    assert len(responses) == 1
    assert responses[0].request_id == "req_011CfNJEiGFRy14RyAtxdZUh"
    assert responses[0].id == "msg_011CfNJEia7VkdqDg9rxsVPV"


def test_a_single_line_response_body_still_parses() -> None:
    body = '{"id": "msg_1", "model": "claude-haiku-4-5-20251001", "usage": {"prompt_tokens": 1}}'
    text = "\n".join([_response_header("req_1"), _line("data:"), _line(body)])

    responses = cw.parse_wire_responses(text)

    assert responses[0].id == "msg_1"


# --- Fail-closed negative controls -------------------------------------------------


def test_a_response_body_with_no_preceding_header_raises() -> None:
    text = "\n".join([_line("data:"), *_response_body("msg_1", "claude-haiku-4-5-20251001")])

    with pytest.raises(cw.CopilotWireError, match="no preceding response"):
        cw.parse_wire_responses(text)


def test_a_body_that_never_decodes_raises() -> None:
    """NEGATIVE CONTROL: a truncated body must not be read as no evidence."""
    text = "\n".join([_response_header("req_1"), _line("data:"), _line("{not json")])

    with pytest.raises(cw.CopilotWireError, match="does not parse as JSON"):
        cw.parse_wire_responses(text)


def test_a_body_that_is_a_json_array_is_never_read_as_a_response() -> None:
    """A JSON array never starts with `{`, so it never matches the response-body

    grammar at all; it is skipped like any other non-matching `[rust:model_wire]`
    line, not raised.
    """
    text = "\n".join([_response_header("req_1"), _line("data:"), _line("[1, 2]")])

    assert cw.parse_wire_responses(text) == []


def test_a_response_missing_id_raises() -> None:
    text = "\n".join(
        [
            _response_header("req_1"),
            _line("data:"),
            _line('{"model": "claude-haiku-4-5-20251001", "usage": {}}'),
        ]
    )

    with pytest.raises(cw.CopilotWireError, match="missing an id"):
        cw.parse_wire_responses(text)


def test_a_request_with_no_model_raises() -> None:
    text = _line('Wire request: {"stream": true}')

    with pytest.raises(cw.CopilotWireError, match="missing a model"):
        cw.parse_wire_requests(text)
