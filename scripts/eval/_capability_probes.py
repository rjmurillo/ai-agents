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
* An override probe whose command does not implement its plan is refused
  before the CLI runs. The argv is caller-supplied and opaque here, so a
  command that omits the override, or targets a different harness, would
  otherwise have its harness default classified as an honored override.
* A subagent tool request is not a launched child, and a concurrency peak
  counts a child only while the stream still holds enough completion
  boundaries to close it. `_capability_topology` owns both rules and the
  event vocabulary they share.
* A harness with no in-tree backend parser observes `EvidenceKind.NONE`, never
  a guess. `_capability_evidence` owns that rule and every other question of
  what a value read from an event stream is worth.
* A missing CLI, a non-zero exit, and a timeout all resolve to `UNVERIFIED`.
  Malformed or truncated output raises `HarnessCapabilityError` instead,
  because a half-read stream is a broken contract rather than a negative
  result.
* `Sol Ultra` is a literal control value. Nothing here folds it onto `high`,
  `xhigh`, `max`, or any other tier, and `_discriminates` is the only
  comparison any value passes through.

Reading the runtime's output lives in `_capability_evidence` and reading child
lifecycles in `_capability_topology`; this module builds the probes, runs them,
and hands what those modules observed to the classifier. It imports what it
calls and re-exports nothing: a caller wanting `observe_model` or
`max_concurrent_children` imports the module that owns it, so the boundary is
visible at the import site.

Authority boundary: provider, model, and pricing tables stay in
`scripts/eval/_providers.py` and `scripts/eval/_eval_common.py`. This module
reads runtime output and records what it observed.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from _capability_evidence import (
    DEFAULT_EFFORT_KEYS,
    observe_effort,
    observe_model,
)
from _capability_topology import (
    max_concurrent_children,
    requested_subagent_tools,
    subagent_lifecycle_events,
)
from _harness_capability import (
    Capability,
    CapabilityStatus,
    EvidenceKind,
    HarnessCapabilityError,
    classify_override,
)
from _runtime_output import RuntimeOutputError, parse_events

Runner = Callable[..., "subprocess.CompletedProcess[str]"]

#: Capabilities this module can probe through `classify_override`.
OVERRIDE_CAPABILITIES: tuple[str, ...] = ("model_override", "effort_override")



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

    The guarantee is enforced here rather than only in `build_override_plan`,
    because this dataclass is public and `probe_override` accepts a hand-built
    plan. `classify_override` compares with `==`, so a plan differing from the
    parent only by case or surrounding whitespace passed that check while a
    case-folding harness would echo the parent back and read as an honored
    override.
    """

    capability: str
    harness: str
    parent_value: str
    child_value: str

    def __post_init__(self) -> None:
        """Refuse a plan this module cannot probe or that cannot discriminate.

        `capability` is checked here rather than only in `build_override_plan`
        for the same reason the rest of these checks moved: `probe_override`
        routes every capability that is not `model_override` through
        `observe_effort`, so a hand-built plan naming anything else would have
        had effort evidence classified as that capability.
        """
        if self.capability not in OVERRIDE_CAPABILITIES:
            raise ProbeError(
                f"capability must be one of {OVERRIDE_CAPABILITIES}, got {self.capability!r}"
            )
        if not self.harness:
            raise ProbeError("harness must be a non-empty string")
        if not self.parent_value:
            raise ProbeError(
                "parent_value must be a non-empty string; an unknown parent cannot discriminate"
            )
        if not _discriminates(self.child_value, self.parent_value):
            raise ProbeError(
                f"child value {self.child_value!r} does not differ from parent "
                f"{self.parent_value!r}; an equal-value request cannot tell an honored "
                "override from a silent inherit"
            )


@dataclass(frozen=True, slots=True)
class ProbeCommand:
    """One CLI invocation, built by the caller.

    `argv` is supplied rather than built here because no Codex flag surface is
    verified in this repository, and inventing one would put an unverified
    contract in the tree. `eval_runtime_parity.build_argv` holds the Copilot
    flag set that is attested.

    Because the argv is opaque to this module, `probe_override` checks that it
    carries the plan's child value before running it. A caller that delivers
    the override some other way must put it in `env` or the probe is refused.
    """

    harness: str
    argv: tuple[str, ...]
    cwd: Path | None = None
    env: Mapping[str, str] | None = None


def _carries_request(command: ProbeCommand, value: str) -> bool:
    """Report whether this invocation actually asks for `value` in its argv.

    `ProbeCommand.argv` is caller-supplied, so nothing else in this module can
    tell a command that requests the override from one that does not. Without
    this check `probe_override` executes an opaque argv and classifies it
    against a plan it may not implement: a command that omits the override
    runs the harness default, and if that default happens to equal the plan's
    child value the probe reports `VERIFIED` for a mechanism that never ran.

    A token carries the request when it is the value itself (`--model`,
    `gpt-5.6-sol`) or ends in `=value` (`--model=gpt-5.6-sol`). A token that
    merely contains the value, such as a prompt mentioning the model name,
    does not.

    Environment variables were accepted here and no longer are: any variable
    whose value happened to equal the request counted as the request, and
    naming the variables that really carry it would mean writing down a Codex
    and Copilot contract this repository has not verified. Argv is the one
    surface a caller can be required to make explicit, so a request delivered
    any other way is refused rather than assumed.

    Known residual gap: this proves the value appears as an argument, not that
    it appears as the *model* or *effort* option, because no verified flag
    surface for either harness exists in this repository. Closing that needs
    step 3 of issue #5423, which is where a real flag set gets observed.
    """
    suffix = f"={value}"
    return any(token == value or token.endswith(suffix) for token in command.argv)


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

    Raises `ProbeError` when `command` does not implement `plan`: a different
    harness, or an invocation that does not carry the plan's child value. Both
    are refused before the CLI runs, because a probe whose command and plan
    describe different invocations cannot attribute what it observes to the
    override it claims to be testing.
    """
    if command.harness != plan.harness:
        raise ProbeError(
            f"command targets {command.harness!r} but the plan probes {plan.harness!r}; "
            "a run against one harness cannot verify an override on another"
        )
    if not command.argv or plan.harness not in Path(command.argv[0]).name:
        # `ProbeCommand.harness` is a caller-supplied label. Nothing tied it to
        # the process actually launched, so a command labelled copilot could
        # execute any executable and have its output classified as copilot's.
        raise ProbeError(
            f"command executes {command.argv[0]!r} if anything, which does not name "
            f"{plan.harness!r}; the label on a command is not evidence of what it runs"
        )
    if not _carries_request(command, plan.child_value):
        raise ProbeError(
            f"command does not request {plan.child_value!r} in its argv or env, so an "
            f"observed {plan.child_value!r} would be the harness default rather than an "
            "honored override"
        )
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
    to a different observable. A `tool_use` block requesting `Agent` or `Task`
    is such an ask, so it is reported and never verifies on its own.
    """
    events, failure = _capture_events(command, runner=runner, timeout=timeout)
    if events is None:
        return Capability(CapabilityStatus.UNVERIFIED, EvidenceKind.NONE, failure)
    launched = subagent_lifecycle_events(events)
    if not launched:
        requested = requested_subagent_tools(events)
        detail = (
            f"{command.harness} output carried {requested} subagent tool requests and no "
            "lifecycle event, so no child is known to have run"
            if requested
            else f"{command.harness} output carried no subagent events"
        )
        return Capability(CapabilityStatus.UNVERIFIED, EvidenceKind.NONE, detail)
    return Capability(
        CapabilityStatus.VERIFIED,
        EvidenceKind.BACKEND,
        f"{command.harness} output carried {len(launched)} subagent lifecycle events",
    )


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
