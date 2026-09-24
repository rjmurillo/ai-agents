"""What a runtime's own output said, and how much that is worth.

Split out of `_capability_probes` after PR #5623's review. That module runs a
harness CLI and classifies the result; this one only reads an event stream and
labels the evidence it found. The seam is the same one that keeps
`_harness_capability` free of subprocess calls: reading, running, and
classifying are three jobs, and a value earns `BACKEND` in exactly one of
them.

Copilot `assistant.message.data.model` is a client label, not backend
evidence (live BYOK capture, Copilot CLI 1.0.89, 2026-09-24): the backend model
is read from the `--log-dir` wire log by `observe_copilot_model`. The codex
shape is different: `codex exec --json` stdout (codex-cli 0.156.0, probed
2026-09-24) names no model or reasoning effort at all. The backend's own
Response object is observable only on the websocket trace enabled with
`RUST_LOG=tungstenite::protocol=trace`. `observe_model`/`observe_effort` read
one agreeing `response.completed` value from that stderr for a single-agent
run; `observe_codex_model`/`observe_codex_effort` read parent and child spans
through `_codex_frames` for runs that spawn children.

Authority boundary: provider, model, and pricing tables stay in
`scripts/eval/_providers.py` and `scripts/eval/_eval_common.py`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from _codex_frames import CodexFrame, ResponseSpan, response_spans
from _copilot_wire import WireRequest, WireResponse
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

#: Harnesses `observe_model` attributes a model to a backend turn for. Claude
#: is absent on purpose: `_runtime_output.claude_result` reads the model off
#: the `system`/`init` event, which the CLI emits before the backend has
#: replied, so it cannot be told apart from the request echoed back. Codex is
#: present, but through `stderr`, not `events`: see `_codex_backend_value` and
#: the module docstring; codex's own branch in `observe_model` runs before
#: this set is consulted. Copilot was removed 2026-09-24 after a live BYOK
#: Anthropic capture showed `assistant.message.data.model` is the requested
#: alias (`claude-haiku-4-5`), not the provider's dated id
#: (`claude-haiku-4-5-20251001`); see
#: `copilot-1.0.89-byok-anthropic/child-model-override.wire.log`. Copilot's
#: backend model is read by `observe_copilot_model` from that wire log.
BACKEND_MODEL_HARNESSES: frozenset[str] = frozenset({"codex"})

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


def _codex_candidate_spans(
    frames: Sequence[CodexFrame],
    attribute: str,
    parent_value: str | None,
) -> list[ResponseSpan]:
    """Return the response spans that answer for a child, not the parent.

    `previous_response_id is None` alone cannot tell a child's first turn
    from the parent's own turn: `codex-0.156.0/subagent-luna-high.trace.log`
    shows the parent starting a *second* chain with no `previous_response_id`
    after its `wait_agent` call returns, so a root-chain count would
    misclassify that wrap-up turn as a fourth child. Filtering by
    `getattr(span, attribute) != parent_value` instead is exact: only a
    span the backend attributes to something other than what the caller
    already knows it asked the parent for can be a child's own answer.
    When no `parent_value` is known (a standalone, non-override probe), the
    first span is excluded instead, mirroring `observe_model`'s treatment of
    the initiating turn as the one that named the request.
    """
    spans: list[ResponseSpan] = response_spans(frames)
    if not spans:
        return []
    if parent_value is not None:
        return [span for span in spans if getattr(span, attribute) != parent_value]
    remainder: list[ResponseSpan] = spans[1:]
    if remainder:
        return remainder
    return spans


def _codex_parent_unconfirmed(
    spans: Sequence[ResponseSpan],
    attribute: str,
    label: str,
    parent_value: str | None,
) -> ProbeObservation | None:
    """Return a NONE observation when `parent_value` is given but no span reports it.

    `None` means the parent is either absent (no-parent-context probe) or
    confirmed by at least one span; either way `_codex_agreement` proceeds.
    """
    if parent_value is None:
        return None
    if any(getattr(span, attribute) == parent_value for span in spans):
        return None
    return ProbeObservation(
        None,
        EvidenceKind.NONE,
        f"no codex response.created frame reported the parent {label} {parent_value!r}; "
        "a child cannot be shown to differ from a baseline that was never observed",
    )


def _codex_agreement(
    frames: Sequence[CodexFrame],
    attribute: str,
    label: str,
    *,
    parent_value: str | None,
) -> ProbeObservation:
    """Resolve a codex child's own value, requiring the parent's to be confirmed first.

    When `parent_value` is given, at least one span must actually report it
    before a child value can verify: a caller's assumed parent value that no
    span ever confirms means the "child differs from parent" comparison has
    no real baseline, only an assumption, and issue #5423 review found this
    repository silently skipped confirming it. With no `parent_value` (a
    standalone, no-parent-context probe), that confirmation step does not
    apply, and the returned detail says so explicitly.
    """
    spans = response_spans(frames)
    if not spans:
        return ProbeObservation(
            None, EvidenceKind.NONE, f"no codex response.created frame carried a {label}"
        )
    unconfirmed = _codex_parent_unconfirmed(spans, attribute, label, parent_value)
    if unconfirmed is not None:
        return unconfirmed
    candidates = _codex_candidate_spans(frames, attribute, parent_value)
    if not candidates:
        return ProbeObservation(
            None,
            EvidenceKind.NONE,
            f"every codex response.created frame reported the parent {label}",
        )
    values = {value for span in candidates if (value := getattr(span, attribute))}
    if len(values) == 1:
        detail = (
            f"codex child response.created frame(s) agreed on {label}"
            if parent_value is not None
            else (
                f"codex response.created frame(s) agreed on {label}; no parent context was "
                "given, so this is the initiating turn's own value, not a confirmed child"
            )
        )
        return ProbeObservation(next(iter(values)), EvidenceKind.BACKEND, detail)
    detail = "disagreed" if values else "carried none"
    return ProbeObservation(
        None, EvidenceKind.NONE, f"codex child response.created frames {detail} on {label}"
    )


def observe_codex_model(
    frames: Sequence[CodexFrame], *, parent_value: str | None = None
) -> ProbeObservation:
    """Read the model codex's own backend attributed to a child's answer.

    Attested from `codex-0.156.0/subagent-luna-high.trace.log` (checked in
    2026-09-24): the parent's `response.created` frames all report
    `model: "gpt-5.6-sol"`; every `spawn_agent`-launched child's
    `response.created` frames report `model: "gpt-6-luna"`. Passing
    `parent_value="gpt-5.6-sol"` isolates the six child frames from the five
    parent frames (see `_codex_candidate_spans`) and returns `BACKEND` with
    `"gpt-6-luna"`, matching this repository's checked-in matrix
    `model_override` cell for codex.
    """
    return _codex_agreement(frames, "model", "model", parent_value=parent_value)


def observe_codex_effort(
    frames: Sequence[CodexFrame], *, parent_value: str | None = None
) -> ProbeObservation:
    """Read the reasoning effort codex's own backend attributed to a child's answer.

    Attested the same way as `observe_codex_model`: the parent's frames in
    `subagent-luna-high.trace.log` report `reasoning.effort: "medium"` and
    every child frame reports `"high"`. `sol-6-low.trace.log` and
    `sol-6-ultra.trace.log` show the single-turn case (`parent_value=None`):
    a lone conversation's own frames agree on the effort it actually ran at
    ("low" and "max" respectively), which is why an `ultra` request never
    reads back as `"ultra"` and `classify_override` correctly withholds
    `VERIFIED` for that literal control value.
    """
    return _codex_agreement(frames, "effort", "effort", parent_value=parent_value)


def _copilot_answer_turns(
    events: Sequence[Mapping[str, object]],
    wire_by_id: Mapping[str, str],
) -> tuple[list[tuple[str | None, str | None]], list[tuple[str | None, str | None]]]:
    """Split answer turns into (parent, child) groups of (backend, client) model pairs.

    A turn is a child's when its event carries a non-empty top-level
    `agentId` (the shape `subagent.started`/`subagent.completed`/
    `assistant.message` all share for a task-tool child, attested in
    `copilot-1.0.89-byok-anthropic/child-model-override.events.jsonl`). The
    backend value comes from `wire_by_id`, keyed by `data.apiCallId`; the
    client value is the event's own `data.model`, kept separately because it
    is the requested alias rather than backend evidence (see
    `observe_copilot_model`).
    """
    parent: list[tuple[str | None, str | None]] = []
    child: list[tuple[str | None, str | None]] = []
    for event in events:
        if event.get("type") != ASSISTANT_EVENT:
            continue
        data = event.get("data")
        if not isinstance(data, Mapping):
            continue
        content = data.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        api_call_id = data.get("apiCallId")
        backend = wire_by_id.get(api_call_id) if isinstance(api_call_id, str) else None
        client = data.get("model")
        client = client if isinstance(client, str) and client else None
        pair = (backend, client)
        (child if event.get("agentId") else parent).append(pair)
    return parent, child


def _backend_agreement(values: set[str]) -> ProbeObservation | None:
    """Resolve a set of matched wire-response models, or defer to the caller.

    Returns `None` when `values` is empty, so `observe_copilot_model` can
    fall through to its client-echo fallback; a non-empty, disagreeing set
    resolves here instead of falling through, because a blended wire answer
    is exactly as inconclusive as a blended client-echoed one.
    """
    if len(values) == 1:
        return ProbeObservation(
            next(iter(values)),
            EvidenceKind.BACKEND,
            "wire response model matched an answer turn's apiCallId",
        )
    if values:
        return ProbeObservation(
            None, EvidenceKind.NONE, "matched wire responses disagreed on model"
        )
    return None


def observe_copilot_model(
    events: Sequence[Mapping[str, object]],
    wire_responses: Sequence[WireResponse],
) -> ProbeObservation:
    """Read the model Copilot's configured provider actually returned.

    Live finding (BYOK Anthropic, copilot-cli 1.0.89, 2026-09-24):
    `assistant.message.data.model` reports the requested alias
    (`claude-haiku-4-5`), not the dated id the provider returned
    (`claude-haiku-4-5-20251001`); the same `apiCallId`/response `id` pair
    carries both in
    `copilot-1.0.89-byok-anthropic/child-model-override.wire.log` versus
    `.events.jsonl`. That makes `data.model` `CLIENT_ECHO`, and the wire
    response body `BACKEND`.

    A child task-tool turn (see `_copilot_answer_turns`) is preferred over a
    parent turn when both exist, the same reasoning `observe_codex_model`
    applies to a spawned child's own frames: a model-override probe wants
    the child's value, not the parent's echoed request.
    """
    wire_by_id = {response.id: response.model for response in wire_responses}
    parent, child = _copilot_answer_turns(events, wire_by_id)
    candidates = child or parent
    if not candidates:
        return ProbeObservation(None, EvidenceKind.NONE, "no copilot answer turn carried a model")
    backend_values = {backend for backend, _ in candidates if backend}
    backend_result = _backend_agreement(backend_values)
    if backend_result is not None:
        return backend_result
    client_values = {client for _, client in candidates if client}
    if len(client_values) == 1:
        return ProbeObservation(
            next(iter(client_values)),
            EvidenceKind.CLIENT_ECHO,
            "assistant.message.model is the requested alias, not the provider's dated id",
        )
    return ProbeObservation(
        None, EvidenceKind.NONE, "no answer turn matched a wire response or a client-echoed model"
    )


def observe_copilot_effort(wire_requests: Sequence[WireRequest]) -> ProbeObservation:
    """Read the reasoning effort Copilot requested from its configured provider.

    The Anthropic response carries no effort or reasoning-tier field at all
    (every response object in `copilot-1.0.89-byok-anthropic/*.wire.log`
    has a `usage` key and never a `reasoning`/`effort` key), so a
    `thinking.budget_tokens` value is always `CLIENT_ECHO`: it is what
    Copilot asked the provider for, never something the provider confirmed
    back. This function has no path to `BACKEND` for that reason, which is
    also why the checked-in matrix records copilot `effort_override` as
    `UNVERIFIED`/`client_echo` rather than `VERIFIED`.
    """
    budgets = {
        request.thinking_budget_tokens
        for request in wire_requests
        if request.thinking_budget_tokens is not None
    }
    if len(budgets) == 1:
        return ProbeObservation(
            str(next(iter(budgets))),
            EvidenceKind.CLIENT_ECHO,
            "thinking.budget_tokens is the requested budget, which the provider never confirms",
        )
    if budgets:
        return ProbeObservation(
            None, EvidenceKind.NONE, "wire requests disagreed on thinking.budget_tokens"
        )
    return ProbeObservation(
        None, EvidenceKind.NONE, "no wire request carried a thinking.budget_tokens value"
    )
