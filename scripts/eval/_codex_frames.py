"""Parse Codex CLI backend evidence from its RUST_LOG trace stderr.

`codex exec --json` stdout carries no model or reasoning effort at all
(verified live against codex-cli 0.156.0 on 2026-09-24: the `response.model`
and `response.reasoning.effort` fields live only inside the OpenAI backend's
own websocket frames, which Codex writes to stderr only when the caller sets
`RUST_LOG=tungstenite::protocol=trace`). This module reads that stderr text
and turns it into structured frames and response spans. It runs no
subprocess and classifies nothing; `_capability_evidence` reads a frame's
worth as evidence, and `_capability_probes` decides when to capture one.

Frame shape, quoted verbatim (keys elided with `...`) from
`tests/eval/fixtures/harness_capability/codex-0.156.0/subagent-luna-high.trace.log`
line 1, a real trimmed capture:

    2026-09-24T12:39:16.716651Z TRACE tungstenite::protocol: Received message
    {"type": "response.created", "response": {"id": "resp_...",
    "model": "gpt-5.6-sol", "status": "in_progress",
    "previous_response_id": null, "reasoning": {"effort": "medium",
    "mode": "standard"}, ...}}

and line 4 of the same file, a function call the parent issued to spawn a
child:

    {"type": "response.output_item.done", "item": {"type": "function_call",
    "name": "spawn_agent", "arguments": "{\\"fork_turns\\": \\"all\\",
    \\"model\\": \\"gpt-6-luna\\", \\"reasoning_effort\\": \\"high\\", ...}"}}

Every line without the marker is ignored: `RUST_LOG=tungstenite::protocol=trace`
also emits Rust log lines this module has no use for. A marker line whose
remainder does not start with `{` is also skipped: the same marker also
carries non-JSON websocket payloads (`Received message Binary
Data<length=4>` and raw bytes; see `parse_codex_frames`). A marker line
whose remainder *does* start with `{` but fails to parse still raises
`CodexFrameError` rather than being skipped, because a truncated or
corrupted JSON frame is a broken capture, not a negative capability result;
`_capability_probes._capture_codex_frames` fails closed the same way
`_capture_events` already does for malformed `--json` stdout.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from _harness_capability import HarnessCapabilityError

#: The exact text `RUST_LOG=tungstenite::protocol=trace` inserts between the
#: log-line timestamp/level prefix and the JSON payload, quoted from the
#: fixtures cited in this module's docstring.
FRAME_MARKER = " TRACE tungstenite::protocol: Received message "


class CodexFrameError(HarnessCapabilityError):
    """A line carrying `FRAME_MARKER` did not parse as a JSON object."""


@dataclass(frozen=True, slots=True)
class CodexFrame:
    """One parsed RUST_LOG trace line: its timestamp prefix and JSON payload."""

    timestamp: str
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ResponseSpan:
    """One backend response lifecycle, `response.created` through completion.

    `created` and `completed` are the frame's 0-based position in the parsed
    frame list, not its content: `peak_overlap` needs relative order to tell
    which spans overlap, and frame order already is chronological order
    because RUST_LOG writes each line as it receives it. `completed` is
    `None` when the frame stream ends before this response's completion
    frame arrives, which is what an in-flight child looks like at the moment
    a capture window closes (see `concurrency-3-requested.trace.log`, where
    every span still completes before the file ends, and a hand-truncated
    capture would not).
    """

    id: str
    model: str
    effort: str | None
    previous_response_id: str | None
    created: int
    completed: int | None


def parse_codex_frames(stderr: str) -> list[CodexFrame]:
    """Parse every RUST_LOG trace frame out of one codex stderr capture.

    Lines without `FRAME_MARKER` are ignored. A live capture also carries
    non-JSON payloads under the very same marker: `Received message Binary
    Data<length=4>` and raw (sometimes non-UTF-8-safe) websocket bytes,
    attested in `codex-0.156.0/thread-limit-1.trace.log`,
    `codex-0.156.0/concurrency-3-requested.trace.log`, and
    `codex-0.156.0/reviewer-isolation.trace.log`. Those are silently
    skipped by checking the remainder's first character before decoding:
    every JSON frame this module cares about is an object, so its remainder
    always starts with `{`. A remainder that *does* start with `{` but
    fails to parse still raises `CodexFrameError`: that is a truncated or
    corrupted JSON frame, a broken capture rather than a binary one, and
    fails closed the same way a malformed frame always has here.
    """
    frames: list[CodexFrame] = []
    for line in stderr.splitlines():
        index = line.find(FRAME_MARKER)
        if index == -1:
            continue
        timestamp = line[:index]
        remainder = line[index + len(FRAME_MARKER) :]
        if not remainder.startswith("{"):
            continue
        try:
            payload = json.loads(remainder)
        except json.JSONDecodeError as exc:
            raise CodexFrameError(
                f"codex trace line does not parse as JSON after the TRACE marker: {exc}"
            ) from exc
        # A JSON value beginning with `{` always decodes to an object (the
        # `startswith("{")` check above), so `payload` is a `dict` here and
        # no further shape check is reachable to test.
        frames.append(CodexFrame(timestamp=timestamp, payload=payload))
    return frames


@dataclass(frozen=True, slots=True)
class _FrameIndex:
    """The bookkeeping `response_spans` needs, kept in frame arrival order."""

    order: list[str]
    created_at: dict[str, int]
    created_response: dict[str, Mapping[str, object]]
    completed_at: dict[str, int]


def _index_response_frames(frames: Sequence[CodexFrame]) -> _FrameIndex:
    """Walk `frames` once, recording each response id's open and close positions.

    A `response.completed` frame for an id with no matching `response.created`
    in this capture opens its own span at that same index rather than being
    dropped: a RUST_LOG capture can start mid-stream, and the completion
    frame carries the same `model`/`reasoning.effort` fields a creation frame
    would, so nothing usable is lost by treating it as both the open and the
    close.
    """
    index = _FrameIndex(order=[], created_at={}, created_response={}, completed_at={})
    for position, frame in enumerate(frames):
        payload = frame.payload
        response = payload.get("response")
        if not isinstance(response, Mapping):
            continue
        response_id = response.get("id")
        if not isinstance(response_id, str) or not response_id:
            continue
        kind = payload.get("type")
        if kind == "response.completed":
            index.completed_at[response_id] = position
        elif kind != "response.created":
            continue
        if response_id not in index.created_at:
            index.created_at[response_id] = position
            index.created_response[response_id] = response
            index.order.append(response_id)
    return index


def response_spans(frames: Sequence[CodexFrame]) -> list[ResponseSpan]:
    """Pair `response.created`/`response.completed` frames into spans, in order.

    See `_index_response_frames` for how a lone completion is handled.
    """
    index = _index_response_frames(frames)
    spans: list[ResponseSpan] = []
    for response_id in index.order:
        response = index.created_response[response_id]
        reasoning = response.get("reasoning")
        effort = reasoning.get("effort") if isinstance(reasoning, Mapping) else None
        model = response.get("model")
        previous = response.get("previous_response_id")
        spans.append(
            ResponseSpan(
                id=response_id,
                model=model if isinstance(model, str) else "",
                effort=effort if isinstance(effort, str) else None,
                previous_response_id=previous if isinstance(previous, str) else None,
                created=index.created_at[response_id],
                completed=index.completed_at.get(response_id),
            )
        )
    return spans


def _function_call_arguments(item: Mapping[str, object]) -> dict[str, object]:
    raw = item.get("arguments")
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def function_calls(frames: Sequence[CodexFrame]) -> list[tuple[str, dict[str, object]]]:
    """Return every `(tool name, arguments)` pair from `response.output_item.done`.

    A function-call item whose `arguments` string does not decode to a JSON
    object contributes an empty argument mapping rather than raising: the
    call itself is still real evidence that the tool was requested, and
    `_capability_probes.probe_subagent_support` only needs the name plus
    whichever arguments did decode.
    """
    calls: list[tuple[str, dict[str, object]]] = []
    for frame in frames:
        if frame.payload.get("type") != "response.output_item.done":
            continue
        item = frame.payload.get("item")
        if not isinstance(item, Mapping) or item.get("type") != "function_call":
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        calls.append((name, _function_call_arguments(item)))
    return calls


def _message_item_texts(item: Mapping[str, object]) -> list[str]:
    """Return every `output_text` string in one `message`-type item's content."""
    content = item.get("content")
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes)):
        return []
    texts: list[str] = []
    for block in content:
        if not isinstance(block, Mapping) or block.get("type") != "output_text":
            continue
        text = block.get("text")
        if isinstance(text, str):
            texts.append(text)
    return texts


def message_texts(frames: Sequence[CodexFrame]) -> list[str]:
    """Return every `output_text` string from a `response.output_item.done` message."""
    texts: list[str] = []
    for frame in frames:
        if frame.payload.get("type") != "response.output_item.done":
            continue
        item = frame.payload.get("item")
        if not isinstance(item, Mapping) or item.get("type") != "message":
            continue
        texts.extend(_message_item_texts(item))
    return texts


def peak_overlap(spans: Sequence[ResponseSpan], *, model: str) -> int | None:
    """Return the max number of completed `model` spans in flight at once.

    Only spans with a `response.completed` frame count: a span that never
    closed within the capture window has no observed end, so it is left out
    of the sweep rather than assumed still running or assumed already done.
    Returns `None` when no span for `model` has completed, which is the same
    "nothing to measure" signal `_capability_topology.max_concurrent_children`
    gives for an incoherent or empty stream.

    Verified against `codex-0.156.0/concurrency-3-requested.trace.log`: three
    `gpt-6-luna` children are requested and their `created`/`completed`
    frame positions interleave so that at most two are open at once (child A
    closes before child C opens; child B stays open across both of the other
    two), matching this repository's checked-in matrix, which records
    `concurrency_limit.value: 2` for that capture.
    """
    completed = [span for span in spans if span.model == model and span.completed is not None]
    if not completed:
        return None
    boundary: list[tuple[int, int]] = []
    for span in completed:
        assert span.completed is not None  # narrowed by the filter above
        boundary.append((span.created, 0))
        boundary.append((span.completed, 1))
    boundary.sort()
    depth = 0
    peak = 0
    for _, kind in boundary:
        if kind == 0:
            depth += 1
            peak = max(peak, depth)
        else:
            depth -= 1
    return peak
