"""What a runtime's own output said, and how much that is worth.

Split out of `_capability_probes` after PR #5623's review. That module runs a
harness CLI and classifies the result; this one only reads an event stream and
labels the evidence it found. The seam is the same one that keeps
`_harness_capability` free of subprocess calls: reading, running, and
classifying are three jobs, and a value earns `BACKEND` in exactly one of
them.

The Copilot shape below (`assistant.message` events carrying `data.model`) is
exercised by recorded fixtures only; no test here runs a real Copilot CLI. The
codex shape is different: `codex exec --json` was probed live 2026-09-24
(codex-cli 0.156.0) and its stdout carries only `thread.started`,
`turn.started`, `item.completed`, and `turn.completed{usage}`; no event names
or attributes a model or reasoning effort at all. The backend's own Response
object is observable only on the client's websocket trace, enabled with
`RUST_LOG=tungstenite::protocol=trace`, one `response.completed` frame per
turn on stderr. `observe_model`/`observe_effort` read codex from `stderr` for
this reason, not from `events`.

Authority boundary: provider, model, and pricing tables stay in
`scripts/eval/_providers.py` and `scripts/eval/_eval_common.py`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from _harness_capability import EvidenceKind
from _runtime_output import copilot_result, structured_tool_model

#: reads the same type, and the model on it is attributable to the turn that
#: produced the text.
ASSISTANT_EVENT = "assistant.message"

#: Session-state events the CLI emits about its own configuration. A value
#: read from one of these is the client reporting what it set, not the backend
#: reporting what it ran, so it is `CLIENT_ECHO` and can never verify.
#: `session.model_change` with `data.newModel` and `data.reasoningEffort` is
#: the shape recorded in `tests/eval/test_providers.py`, whose comment states
#: it is modeled on a real log.
SESSION_STATE_EVENTS: frozenset[str] = frozenset({"session.model_change", "session.start"})

#: Keys an assistant turn might carry a resolved reasoning effort or tier on.
#: Only `reasoningEffort` is attested in-tree, and only on a session-state
#: event. The rest are candidates. A key that never matches yields
#: `EvidenceKind.NONE`, so a wrong guess here withholds a claim rather than
#: inventing one. A live run should replace this with the observed key.
DEFAULT_EFFORT_KEYS: tuple[str, ...] = ("reasoningEffort", "reasoning_effort", "effort")

#: Harnesses with an in-tree parser that attributes a model to a backend turn.
#: Claude is absent on purpose: `_runtime_output.claude_result` reads the model
#: off the `system`/`init` event, which the CLI emits before the backend has
#: replied, so it cannot be told apart from the request echoed back. Codex is
#: present, but through `stderr`, not `events`: see `_codex_backend_value` and
#: the module docstring. Membership here documents which harnesses
#: `observe_model` can attribute a model for at all; codex's own branch in
#: `observe_model` runs before this set is consulted.
BACKEND_MODEL_HARNESSES: frozenset[str] = frozenset({"codex", "copilot"})

#: The verbatim text codex-cli's TRACE line emits immediately before the raw
#: JSON body of a frame it *received* from the backend
#: (`RUST_LOG=tungstenite::protocol=trace`), one line per frame. A frame's own
#: JSON begins right after this prefix on the same line. Requiring that
#: adjacency, instead of searching the whole line for the substring
#: `{"type":"response.completed"` anywhere in it, is what rejects a
#: client-sent `Sending message` line whose request body embeds a *prior*
#: turn's `"type":"response.completed"` (for example
#: `Sending message {"type":"response.create","prior":{"type":"response.completed",...}}}`)
#: and rejects a non-trace line that merely echoes the same substring (for
#: example `codex echo: {"type":"response.completed",...}`). Quoted from a
#: live capture, probed 2026-09-24, codex-cli 0.156.0:
#: ``2026-09-24T12:36:36.792998Z TRACE tungstenite::protocol: Received message
#: {"type":"response.completed","response":{...,"model":"gpt-5.6-terra",...,
#: "reasoning":{"context":"all_turns","effort":"low","mode":"standard",
#: "summary":null},...}}``
_CODEX_TRACE_RECEIVED_PREFIX = "tungstenite::protocol: Received message "


def _codex_response_completed_frames(stderr: str) -> list[Mapping[str, object]]:
    """Return every backend `response.completed` frame in codex TRACE stderr.

    A frame's JSON body must start immediately after
    `_CODEX_TRACE_RECEIVED_PREFIX` on its line; `JSONDecoder.raw_decode`
    starting at that offset reads exactly the JSON object and ignores
    trailing log text a `TimeoutExpired` capture might append. A candidate is
    kept only when the decoded top-level value is a mapping, its `type` is
    exactly `"response.completed"`, and it carries a `response` mapping.
    Anything else (decode failure, non-mapping, wrong `type`, missing or
    non-mapping `response`) is skipped rather than raised: malformed TRACE
    output is not this function's contract to police, only which frames count
    as the backend's own report.
    """
    decoder = json.JSONDecoder()
    frames: list[Mapping[str, object]] = []
    for line in stderr.splitlines():
        offset = line.find(_CODEX_TRACE_RECEIVED_PREFIX)
        if offset == -1:
            continue
        json_start = offset + len(_CODEX_TRACE_RECEIVED_PREFIX)
        try:
            frame, _end = decoder.raw_decode(line, json_start)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(frame, Mapping)
            and frame.get("type") == "response.completed"
            and isinstance(frame.get("response"), Mapping)
        ):
            frames.append(frame)
    return frames


def _codex_backend_value(stderr: str, path: tuple[str, ...]) -> str | None:
    """Return the single value at `path` across all `response.completed` frames.

    Two frames disagreeing return `None`, mirroring `_assistant_values`: a
    blended answer has no single author, so no value earns the claim. `path`
    walks nested mappings, for example `("response", "reasoning", "effort")`.
    """
    found: set[str] = set()
    for frame in _codex_response_completed_frames(stderr):
        node: object = frame
        for key in path:
            if not isinstance(node, Mapping):
                node = None
                break
            node = node.get(key)
        if isinstance(node, str) and node:
            found.add(node)
    return found.pop() if len(found) == 1 else None


def _observe_codex_backend(stderr: str, label: str, path: tuple[str, ...]) -> ProbeObservation:
    """Read one field off codex's `response.completed` frames, or NONE closed.

    A stderr with no `response.completed` frame at all almost always means the
    caller ran without `RUST_LOG=tungstenite::protocol=trace`, so that is
    named explicitly rather than folded into the generic "frames disagreed"
    message below, which is for the rarer case of a trace that did capture
    frames that do not agree.
    """
    if _CODEX_TRACE_RECEIVED_PREFIX not in stderr:
        return ProbeObservation(
            None,
            EvidenceKind.NONE,
            "codex stderr carried no response.completed frame; rerun with "
            "RUST_LOG=tungstenite::protocol=trace to capture the backend Response object",
        )
    value = _codex_backend_value(stderr, path)
    if value is None:
        return ProbeObservation(
            None,
            EvidenceKind.NONE,
            f"codex response.completed frames disagreed on {label}, or none carried it",
        )
    return ProbeObservation(
        value, EvidenceKind.BACKEND, f"codex response.completed frame carried {label}"
    )

@dataclass(frozen=True, slots=True)
class ProbeObservation:
    """What the runtime's own output said, and how much that is worth."""

    observed: str | None
    evidence: EvidenceKind
    detail: str


def _assistant_values(
    events: Sequence[Mapping[str, object]],
    keys: Sequence[str],
) -> str | None:
    """Return the single value `keys` carries on a backend answer turn.

    Requires non-empty text content on the same event, which is what makes the
    turn an answer the backend produced rather than a status line. Two turns
    disagreeing return `None`, mirroring `copilot_result`: a blended answer has
    no single author, so no value earns the claim.
    """
    found: set[str] = set()
    for event in events:
        if event.get("type") != ASSISTANT_EVENT:
            continue
        data = event.get("data")
        if not isinstance(data, Mapping):
            continue
        content = data.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value:
                found.add(value)
                break
    return found.pop() if len(found) == 1 else None


def _session_state_value(
    events: Sequence[Mapping[str, object]],
    keys: Sequence[str],
) -> str | None:
    """Return a value the CLI reported about its own session configuration."""
    for event in events:
        kind = event.get("type")
        if not isinstance(kind, str) or kind not in SESSION_STATE_EVENTS:
            continue
        data = event.get("data")
        if not isinstance(data, Mapping):
            continue
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def observe_model(
    harness: str,
    events: Sequence[Mapping[str, object]],
    *,
    stderr: str = "",
) -> ProbeObservation:
    """Read the model the backend attributed to its own answer.

    Codex is read from `stderr`, not `events`: see the module docstring and
    `_observe_codex_backend`. `events` is unused for codex; the parameter is
    still accepted so callers share one call shape across harnesses.
    """
    if harness == "codex":
        return _observe_codex_backend(stderr, "model", ("response", "model"))
    if harness not in BACKEND_MODEL_HARNESSES:
        return ProbeObservation(
            None,
            EvidenceKind.NONE,
            f"no in-tree parser attributes a model to a backend turn for {harness}",
        )
    _, model = copilot_result(events)
    if not model:
        model = structured_tool_model(events)
    if model:
        return ProbeObservation(model, EvidenceKind.BACKEND, "model attributed to an answer turn")
    echoed = _session_state_value(events, ("newModel", "selectedModel", "model"))
    if echoed:
        return ProbeObservation(
            echoed,
            EvidenceKind.CLIENT_ECHO,
            "model came from a session-state event, which is the request echoed back",
        )
    return ProbeObservation(None, EvidenceKind.NONE, "no answer turn carried a model attribution")


def observe_effort(
    harness: str,
    events: Sequence[Mapping[str, object]],
    *,
    effort_keys: Sequence[str] = DEFAULT_EFFORT_KEYS,
    stderr: str = "",
) -> ProbeObservation:
    """Read the reasoning effort or tier the backend attributed to its answer.

    Codex is read from `stderr`, not `events`, same as `observe_model`.
    `effort_keys` does not apply to codex: its field is always
    `response.reasoning.effort`, a fixed path on a frame this module already
    decoded rather than a key name to search assistant turns for.
    """
    if harness == "codex":
        return _observe_codex_backend(stderr, "effort", ("response", "reasoning", "effort"))
    observed = _assistant_values(events, effort_keys)
    if observed:
        return ProbeObservation(
            observed, EvidenceKind.BACKEND, f"{harness} answer turn carried a resolved effort"
        )
    echoed = _session_state_value(events, effort_keys)
    if echoed:
        return ProbeObservation(
            echoed,
            EvidenceKind.CLIENT_ECHO,
            "effort came from a session-state event, which is the request echoed back",
        )
    return ProbeObservation(None, EvidenceKind.NONE, f"no {harness} answer turn carried an effort")
