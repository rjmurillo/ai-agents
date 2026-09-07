"""What a runtime's own output said, and how much that is worth.

Split out of `_capability_probes` after PR #5623's review. That module runs a
harness CLI and classifies the result; this one only reads an event stream and
labels the evidence it found. The seam is the same one that keeps
`_harness_capability` free of subprocess calls: reading, running, and
classifying are three jobs, and a value earns `BACKEND` in exactly one of
them.

Nothing here has been executed against a real Codex or Copilot CLI. Every
shape below is exercised by recorded output only.

Authority boundary: provider, model, and pricing tables stay in
`scripts/eval/_providers.py` and `scripts/eval/_eval_common.py`.
"""

from __future__ import annotations

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
#: absent because no Codex output parser exists in this repository at all.
BACKEND_MODEL_HARNESSES: frozenset[str] = frozenset({"copilot"})

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
) -> ProbeObservation:
    """Read the model the backend attributed to its own answer."""
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
) -> ProbeObservation:
    """Read the reasoning effort or tier the backend attributed to its answer."""
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
