"""Parse Copilot CLI backend wire evidence from `--log-level all --log-dir`.

Live finding (BYOK Anthropic, copilot-cli 1.0.89, 2026-09-24):
`assistant.message.data.model` in `--output-format json` stdout reports the
*requested* model alias (for example `claude-haiku-4-5`), not the dated id
the Anthropic provider actually returned (`claude-haiku-4-5-20251001`). That
field is therefore a client label, not backend evidence: see
`_capability_evidence.observe_copilot_model`, which reads the provider's own
model id instead, from the debug log this module parses.

The only place the provider's own response appears is the debug log written
by `--log-level all --log-dir <dir>`, as lines shaped
`<ts> [DEBUG] [rust:model_wire] ...`. A real capture pretty-prints the JSON
body across many lines, and **only the first line of that body carries the
timestamp and `[rust:model_wire] ` prefix; every continuation line is the
raw JSON fragment with no prefix at all.** Quoted verbatim from
`tests/eval/fixtures/harness_capability/copilot-1.0.89-byok-anthropic/child-model-override.wire.log`:

    2026-09-24T12:53:39.142Z [DEBUG] [rust:model_wire] Wire request: {
      "model": "claude-haiku-4-5",
      "thinking": {"type": "enabled", "budget_tokens": 1024, ...},
      "stream": true
    }
    2026-09-24T12:53:42.980Z [DEBUG] [rust:model_wire] response
    (Request-ID req_011CfNJDUzW6nVxxNRzag79E):
    2026-09-24T12:53:42.980Z [DEBUG] [rust:model_wire] data:
    2026-09-24T12:53:42.980Z [DEBUG] [rust:model_wire] {
      "id": "msg_011CfNJDVR4jT9eJxMAuAXzF", "object": "chat.completion",
      "model": "claude-haiku-4-5-20251001", "usage": {...}
    }

A response's `id` matches the `apiCallId` field Copilot's own
`assistant.message` event carries for the same turn, which is how
`_capability_evidence.observe_copilot_model` attributes a wire response to
one answer turn.

Other log lines, under a different `[rust:...]` marker entirely, can appear
interleaved between a `response (Request-ID ...):` header and the
`[rust:model_wire] {` line that actually opens its body (see
`copilot-1.0.89-byok-anthropic/concurrency-3-requested.wire.log`, whose
`req_011CfNJEiGFRy14RyAtxdZUh` header is followed by six
`[rust:copilot_runtime::...]` lines before its body starts; the pre-multi-line
parser this module replaced could not skip over them and silently lost two
of that fixture's six responses). This module's grammar: a body begins at a
`[rust:model_wire]` line whose remainder starts with `{` (a response) or
`Wire request: {` (a request), and that body's text is every line from there
up to, but not including, the next line that starts with an ISO-8601
timestamp, regardless of that next line's own marker. A response body pairs
with the most recently seen `response (Request-ID ...)` header, which is why
the interleaved lines above cannot break the pairing: they carry no header
of their own, so `pending_request_id` is untouched by them.

The accumulated body text is decoded with `json.JSONDecoder().raw_decode`,
which needs only a valid JSON value at the start of the text, not the whole
text to be exactly one value; trailing bytes (there are none in any fixture)
are ignored the same way they would be for a single-line body. A body that
still fails to decode raises `CopilotWireError`: a truncated or corrupted
body is a broken capture, not a negative capability result, matching how
`_codex_frames.parse_codex_frames` treats a malformed `{`-prefixed frame.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from _harness_capability import HarnessCapabilityError

#: The text every `[rust:model_wire]` log line's *first* line carries after
#: its timestamp and level prefix. Continuation lines of a multi-line body
#: carry no marker, and no prefix, at all.
_MARKER = "[rust:model_wire] "
_REQUEST_PREFIX = "Wire request: "
_RESPONSE_HEADER_PREFIX = "response (Request-ID "

#: `YYYY-MM-DDTHH:MM:SS`, the prefix every log line this module reads starts
#: a *new* line with. A continuation line of a pretty-printed JSON body
#: never starts this way, which is what lets `_read_body` find a body's end
#: without needing to know its shape.
_NEW_LINE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


class CopilotWireError(HarnessCapabilityError):
    """A `[rust:model_wire]` line or block did not parse as the documented shape."""


@dataclass(frozen=True, slots=True)
class WireRequest:
    """One outbound request Copilot sent to its configured model provider."""

    model: str
    thinking_budget_tokens: int | None


@dataclass(frozen=True, slots=True)
class WireResponse:
    """One inbound response Copilot's model provider returned.

    `id` is the value the CLI's own `assistant.message.data.apiCallId`
    repeats for the answer turn this response produced, which is the join
    key `_capability_evidence.observe_copilot_model` uses.
    """

    request_id: str
    id: str
    model: str
    usage: Mapping[str, object]


def _starts_new_line(text: str) -> bool:
    """Return whether `text` opens a new log line rather than continuing one.

    A JSON continuation fragment (indentation, a quoted string, a brace)
    cannot itself match `YYYY-MM-DDTHH:MM:SS` at its very start, so this is
    exact for the shapes these logs actually carry.
    """
    return _NEW_LINE_PREFIX.match(text) is not None


def _read_body(lines: list[str], first_line: str, after: int) -> tuple[Mapping[str, object], int]:
    """Join `first_line` with `lines[after:]` up to the next new log line, then decode.

    `first_line` always starts with `{` (both call sites in `_scan` check
    this before calling), and a JSON value beginning with `{` always decodes
    to an object, so no further shape check on `payload` is reachable to
    test.
    """
    body = [first_line]
    index = after
    while index < len(lines) and not _starts_new_line(lines[index]):
        body.append(lines[index])
        index += 1
    text = "\n".join(body)
    try:
        payload, _ = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError as exc:
        raise CopilotWireError(f"copilot wire body does not parse as JSON: {exc}") from exc
    return payload, index


def _build_request(payload: Mapping[str, object]) -> WireRequest:
    model = payload.get("model")
    if not isinstance(model, str) or not model:
        raise CopilotWireError("copilot wire request is missing a model")
    thinking = payload.get("thinking")
    budget = thinking.get("budget_tokens") if isinstance(thinking, Mapping) else None
    return WireRequest(
        model=model, thinking_budget_tokens=budget if isinstance(budget, int) else None
    )


def _build_response(payload: Mapping[str, object], request_id: str) -> WireResponse:
    response_id = payload.get("id")
    model = payload.get("model")
    if not isinstance(response_id, str) or not response_id:
        raise CopilotWireError(f"copilot wire response for {request_id!r} is missing an id")
    if not isinstance(model, str) or not model:
        raise CopilotWireError(f"copilot wire response for {request_id!r} is missing a model")
    usage = payload.get("usage")
    return WireResponse(
        request_id=request_id,
        id=response_id,
        model=model,
        usage=usage if isinstance(usage, Mapping) else {},
    )


def _scan(log_text: str) -> tuple[list[WireRequest], list[WireResponse]]:
    """Walk one debug log once, in order, producing every request and response.

    A response body found with no preceding `response (Request-ID ...)`
    header raises: an unpaired response cannot be attributed to any turn,
    which is exactly the ambiguity `observe_copilot_model` depends on this
    module to have already resolved.
    """
    lines = log_text.splitlines()
    requests: list[WireRequest] = []
    responses: list[WireResponse] = []
    pending_request_id: str | None = None
    index = 0
    while index < len(lines):
        marker_at = lines[index].find(_MARKER)
        if marker_at == -1:
            index += 1
            continue
        remainder = lines[index][marker_at + len(_MARKER) :]
        if remainder.startswith(_RESPONSE_HEADER_PREFIX):
            pending_request_id = remainder[len(_RESPONSE_HEADER_PREFIX) :].rstrip(":").rstrip(")")
            index += 1
        elif remainder.startswith(_REQUEST_PREFIX) and remainder[len(_REQUEST_PREFIX) :].startswith(
            "{"
        ):
            payload, index = _read_body(lines, remainder[len(_REQUEST_PREFIX) :], index + 1)
            requests.append(_build_request(payload))
        elif remainder.startswith("{"):
            if pending_request_id is None:
                raise CopilotWireError(
                    "copilot wire log has a response body with no preceding "
                    "response (Request-ID ...) header"
                )
            payload, index = _read_body(lines, remainder, index + 1)
            responses.append(_build_response(payload, pending_request_id))
            pending_request_id = None
        else:
            index += 1
    return requests, responses


def parse_wire_requests(log_text: str) -> list[WireRequest]:
    """Parse every `Wire request: {...}` body in one Copilot debug log."""
    requests, _ = _scan(log_text)
    return requests


def parse_wire_responses(log_text: str) -> list[WireResponse]:
    """Parse every response body in one Copilot debug log, paired to its header."""
    _, responses = _scan(log_text)
    return responses
