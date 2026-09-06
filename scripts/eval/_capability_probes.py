"""Behavioral capability probers for the #5422 orchestration experiment.

Step 2 of issue #5423. `_harness_capability` classifies evidence a caller
supplies and makes zero subprocess calls; this module is that caller. It runs a
harness CLI through an injected runner, reads the runtime's own event stream,
and hands what it found to the existing classifiers. The split is deliberate:
gathering lives here, classification stays there, and neither file grows a copy
of the other's job.

Nothing in this module has been executed against a real Codex or Copilot CLI.
Step 3 of the issue (live runs, paid spend) is not authorized in the
environment this was written in, so every path here is exercised only by
injected fake runners and recorded output shapes. That is also why no function
here writes to `examples/harness-capability-matrix.json`: every cell in the
checked-in matrix stays UNVERIFIED until a live run produces evidence.

Fail-closed rules, each of which can only ever refuse a claim:

* `VERIFIED` is reachable only from `EvidenceKind.BACKEND`, and only through
  `_harness_capability.classify_override` or the two presence gates below.
* An override plan whose child request does not differ from the parent value
  cannot be constructed. `classify_override` returns `UNVERIFIED` for equal
  values, so such a plan is a probe that can never verify anything; building
  one silently would waste a live run and read as a failed capability.
* A harness with no in-tree backend parser observes `EvidenceKind.NONE`, never
  a guess.
* A missing CLI, a non-zero exit, and a timeout all resolve to `UNVERIFIED`.
  Malformed or truncated output raises `HarnessCapabilityError` instead,
  because a half-read stream is a broken contract rather than a negative
  result.
* `Sol Ultra` is a literal control value. Nothing here folds it onto `high`,
  `xhigh`, `max`, or any other tier, and `_discriminates` is the only
  comparison any value passes through.

Authority boundary: provider, model, and pricing tables stay in
`scripts/eval/_providers.py` and `scripts/eval/_eval_common.py`. This module
reads runtime output and records what it observed.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from _harness_capability import (
    Capability,
    CapabilityStatus,
    EvidenceKind,
    HarnessCapabilityError,
    classify_override,
)
from _runtime_output import (
    RuntimeOutputError,
    copilot_result,
    parse_events,
    structured_tool_model,
    traces,
)

Runner = Callable[..., "subprocess.CompletedProcess[str]"]

#: Capabilities this module can probe through `classify_override`.
OVERRIDE_CAPABILITIES: tuple[str, ...] = ("model_override", "effort_override")

#: The event type Copilot attaches a backend answer to. `copilot_result`
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

_START_HINTS: tuple[str, ...] = ("start", "begin", "launch", "spawn")
_END_HINTS: tuple[str, ...] = ("complete", "end", "stop", "finish", "exit", "result")


class ProbeError(HarnessCapabilityError):
    """A probe could not be constructed or its output could not be trusted.

    Subclasses `HarnessCapabilityError` so callers that already fail closed on
    the capability-matrix contract keep doing so without a second except arm.
    """


@dataclass(frozen=True, slots=True)
class OverridePlan:
    """A model or effort override probe that can discriminate a real override.

    `child_value` is guaranteed to differ from `parent_value`, so an observed
    match means the override mechanism ran rather than the child inheriting.
    Both values are the caller's verbatim strings; nothing normalizes them.
    """

    capability: str
    harness: str
    parent_value: str
    child_value: str


@dataclass(frozen=True, slots=True)
class ProbeCommand:
    """One CLI invocation, built by the caller.

    `argv` is supplied rather than built here because no Codex flag surface is
    verified in this repository, and inventing one would put an unverified
    contract in the tree. `eval_runtime_parity.build_argv` holds the Copilot
    flag set that is attested.
    """

    harness: str
    argv: tuple[str, ...]
    cwd: Path | None = None
    env: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class ProbeObservation:
    """What the runtime's own output said, and how much that is worth."""

    observed: str | None
    evidence: EvidenceKind
    detail: str


def _discriminates(candidate: str, parent: str) -> bool:
    """Report whether `candidate` can tell an honored override from an inherit.

    Stricter than `classify_override`, which compares with `==`: a candidate
    differing from the parent only by case or surrounding whitespace is
    rejected here, because a harness that case-folds its own values would
    report the parent's value back and look like a successful override.
    Rejecting is the fail-closed direction; it withholds a probe rather than
    accepting a weaker one.

    This is not normalization of the values themselves. Neither string is
    rewritten, mapped, or aliased, and `Sol Ultra` reaches `OverridePlan`
    exactly as it was passed in.
    """
    return candidate.strip().casefold() != parent.strip().casefold()


def build_override_plan(
    *,
    capability: str,
    harness: str,
    parent_value: str,
    candidates: Sequence[str],
) -> OverridePlan:
    """Select a child request that differs from the parent, or fail closed.

    Raises `ProbeError` when no candidate discriminates. That is the point of
    the function: `classify_override` returns `UNVERIFIED` when the requested
    value equals the parent's, so a plan built from an equal value is a probe
    that spends a live run and can never verify anything. PR #5547 focus area 1
    and the reopen comment on issue #5423 both name this trap, so it is made
    unconstructible rather than merely documented.
    """
    if capability not in OVERRIDE_CAPABILITIES:
        raise ProbeError(f"capability must be one of {OVERRIDE_CAPABILITIES}, got {capability!r}")
    if not harness:
        raise ProbeError("harness must be a non-empty string")
    if not parent_value:
        raise ProbeError(
            "parent_value must be a non-empty string; an unknown parent cannot discriminate"
        )
    usable = [value for value in candidates if value and _discriminates(value, parent_value)]
    if not usable:
        raise ProbeError(
            f"no candidate for {harness} {capability} differs from the parent value "
            f"{parent_value!r}; an equal-value request cannot tell an honored override "
            "from a silent inherit"
        )
    return OverridePlan(
        capability=capability,
        harness=harness,
        parent_value=parent_value,
        child_value=usable[0],
    )


def _capture_events(
    command: ProbeCommand,
    *,
    runner: Runner,
    timeout: float,
) -> tuple[list[dict[str, object]] | None, str]:
    """Run one probe and return its events, or a reason it produced none.

    A missing CLI, a failed launch, a timeout, and a non-zero exit return
    `(None, reason)` so the caller records `UNVERIFIED`. Malformed or empty
    output raises, because output that cannot be parsed says nothing about the
    capability and must not be read as a negative result either.
    """
    try:
        run = runner(
            list(command.argv),
            cwd=command.cwd,
            env=dict(command.env) if command.env is not None else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return None, f"{command.argv[0]} is not on PATH: {exc}"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{command.harness} probe did not complete: {exc}"
    if run.returncode != 0:
        stderr = (run.stderr or "").strip()
        return None, stderr or f"{command.harness} probe exited with code {run.returncode}"
    try:
        events = parse_events(run.stdout or "")
    except RuntimeOutputError as exc:
        raise ProbeError(f"{command.harness} probe output is malformed: {exc}") from exc
    if not events:
        raise ProbeError(
            f"{command.harness} probe exited 0 with no events; the output is empty or truncated"
        )
    return events, ""


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


def probe_override(
    plan: OverridePlan,
    command: ProbeCommand,
    *,
    runner: Runner,
    timeout: float,
    effort_keys: Sequence[str] = DEFAULT_EFFORT_KEYS,
) -> Capability:
    """Run one override probe and classify it with the existing classifier.

    Classification is not reimplemented here: the observed value, its evidence
    kind, and the plan's parent value go straight to
    `_harness_capability.classify_override`, which owns every rule that can
    withhold `VERIFIED`.
    """
    events, failure = _capture_events(command, runner=runner, timeout=timeout)
    if events is None:
        return Capability(CapabilityStatus.UNVERIFIED, EvidenceKind.NONE, failure)
    observation = (
        observe_model(plan.harness, events)
        if plan.capability == "model_override"
        else observe_effort(plan.harness, events, effort_keys=effort_keys)
    )
    status = classify_override(
        plan.child_value,
        observation.observed,
        observation.evidence,
        parent_value=plan.parent_value,
    )
    return Capability(
        status=status,
        evidence=observation.evidence,
        detail=(
            f"requested {plan.child_value!r} against parent {plan.parent_value!r}; "
            f"observed {observation.observed!r} ({observation.detail})"
        ),
    )


def probe_subagent_support(
    command: ProbeCommand,
    *,
    runner: Runner,
    timeout: float,
) -> Capability:
    """Verify the harness actually launched a child, from its own event stream.

    Presence, not a requested count: a run that asked for children and shows
    none in its output is `UNVERIFIED`, which is the config-echo rule applied
    to a different observable.
    """
    events, failure = _capture_events(command, runner=runner, timeout=timeout)
    if events is None:
        return Capability(CapabilityStatus.UNVERIFIED, EvidenceKind.NONE, failure)
    _, subagents = traces(events)
    if not subagents:
        return Capability(
            CapabilityStatus.UNVERIFIED,
            EvidenceKind.NONE,
            f"{command.harness} output carried no subagent events",
        )
    return Capability(
        CapabilityStatus.VERIFIED,
        EvidenceKind.BACKEND,
        f"{command.harness} output carried {len(subagents)} subagent events",
    )


def max_concurrent_children(events: Sequence[Mapping[str, object]]) -> int | None:
    """Return the peak number of children in flight at once, or `None`.

    Derived by walking subagent start and completion boundaries in order, so
    the result is what the runtime reported running, never what the probe
    asked for. Returns `None` when no completion boundary appears: without
    one, a run of N starts is indistinguishable from N sequential children,
    and assuming they overlapped would report the requested number wearing the
    observed number's label. Claude's `tool_use` blocks for `Agent` and `Task`
    carry no boundary of either kind, so they resolve to `None` here.
    """
    depth = 0
    peak = 0
    saw_end = False
    for event in events:
        kind = event.get("type")
        if not isinstance(kind, str) or "subagent" not in kind.lower():
            continue
        lowered = kind.lower()
        if any(hint in lowered for hint in _END_HINTS):
            depth = max(0, depth - 1)
            saw_end = True
        elif any(hint in lowered for hint in _START_HINTS):
            depth += 1
            peak = max(peak, depth)
    if not saw_end or peak == 0:
        return None
    return peak


def probe_concurrency(
    command: ProbeCommand,
    *,
    requested: int,
    runner: Runner,
    timeout: float,
) -> Capability:
    """Measure the maximum children actually running at once.

    `requested` is recorded in the detail text and never becomes the value.
    A harness that was asked for four children and ran two records two.
    """
    if requested < 1:
        raise ProbeError("requested concurrency must be at least 1")
    events, failure = _capture_events(command, runner=runner, timeout=timeout)
    if events is None:
        return Capability(CapabilityStatus.UNVERIFIED, EvidenceKind.NONE, failure)
    peak = max_concurrent_children(events)
    if peak is None:
        return Capability(
            CapabilityStatus.UNVERIFIED,
            EvidenceKind.NONE,
            f"{command.harness} output has no paired subagent start and completion boundaries, "
            f"so concurrency cannot be derived (requested {requested})",
        )
    return Capability(
        CapabilityStatus.VERIFIED,
        EvidenceKind.BACKEND,
        f"{command.harness} ran at most {peak} children at once while {requested} were requested",
        value=peak,
    )
