# taste-lint: ignore file-size
# file-size suppression rationale: probe command validation, event parsing, and
# fail-closed capability classification share one auditable boundary.
"""Behavioral capability probers for the #5422 orchestration experiment.

The `_harness_capability` module classifies evidence and makes zero
subprocess calls; this module is that caller. It runs a harness CLI through an
injected runner, reads the runtime's own event stream, and hands what it found
to the existing classifiers. The JSON plan loader is shell-free and validates
each command before execution. The split is deliberate: gathering lives here,
classification stays there, and neither file grows a copy of the other's job.

This module never writes to `examples/harness-capability-matrix.json`. A
caller can write a report after a live run, but each cell remains UNVERIFIED
unless the runtime supplies the backend evidence required by the classifier.

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

import json
import shutil
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
    subagent_launch_count,
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

    Because the argv is opaque to this module, `probe_override` checks that the
    typed `request_flag` carries the plan's child value before running it. JSON
    plans use that field to render the value into argv, so unrelated arguments
    cannot satisfy the override check.
    """

    harness: str
    argv: tuple[str, ...]
    cwd: Path | None = None
    env: Mapping[str, str] | None = None
    request_flag: str | None = None


@dataclass(frozen=True, slots=True)
class BehavioralProbe:
    """One JSON-configured behavioral probe."""

    capability: str
    harness: str
    command: ProbeCommand
    parent_value: str | None = None
    child_value: str | None = None
    requested: int | None = None

    def __post_init__(self) -> None:
        supported = (*OVERRIDE_CAPABILITIES, "subagent_support", "concurrency_limit")
        if self.capability not in supported:
            raise ProbeError(f"capability must be one of {supported}, got {self.capability!r}")
        if self.command.harness != self.harness:
            raise ProbeError(
                f"command targets {self.command.harness!r} but the plan names {self.harness!r}"
            )
        if self.capability in OVERRIDE_CAPABILITIES and (
            not self.parent_value or not self.child_value
        ):
            raise ProbeError(f"{self.capability} requires non-empty parent_value and child_value")
        if (
            self.capability in OVERRIDE_CAPABILITIES
            and self.parent_value is not None
            and self.child_value is not None
            and not _discriminates(self.child_value, self.parent_value)
        ):
            raise ProbeError(
                f"child value {self.child_value!r} does not differ from parent "
                f"{self.parent_value!r}; an equal-value request cannot tell an honored "
                "override from a silent inherit"
            )
        if self.capability == "concurrency_limit" and (
            not isinstance(self.requested, int)
            or isinstance(self.requested, bool)
            or self.requested < 1
        ):
            raise ProbeError("concurrency_limit requires requested >= 1")


def _carries_request(command: ProbeCommand, value: str) -> bool:
    """Return whether the typed request flag is bound to the requested value."""
    flag = command.request_flag
    if flag is None:
        return False
    joined = f"{flag}={value}"
    return any(
        token == joined
        or (token == flag and index + 1 < len(command.argv) and command.argv[index + 1] == value)
        for index, token in enumerate(command.argv)
    )


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


def _validate_command(
    command: ProbeCommand,
    *,
    executable_allowlist: Mapping[str, Path] | None = None,
) -> None:
    if not command.harness:
        raise ProbeError("command harness must be non-empty")
    if not command.argv:
        raise ProbeError("command argv must be non-empty")
    if any("\x00" in argument for argument in command.argv):
        raise ProbeError("command argv must not contain NUL bytes")
    if command.cwd is not None and "\x00" in str(command.cwd):
        raise ProbeError("command cwd must not contain NUL bytes")
    if command.env is not None and any(
        "\x00" in key or "\x00" in value for key, value in command.env.items()
    ):
        raise ProbeError("command environment must not contain NUL bytes")
    if command.request_flag is not None and "\x00" in command.request_flag:
        raise ProbeError("command request_flag must not contain NUL bytes")
    if executable_allowlist is None:
        if Path(command.argv[0]).name != command.harness:
            raise ProbeError(
                f"command executes {command.argv[0]!r}, which does not name {command.harness!r}"
            )
        return
    expected = executable_allowlist.get(command.harness)
    actual_name = shutil.which(command.argv[0])
    if expected is None or actual_name is None:
        raise ProbeError(
            f"command executable {command.argv[0]!r} is not configured for {command.harness!r}"
        )
    actual = Path(actual_name).resolve()
    if actual != expected.resolve():
        raise ProbeError(
            f"command executable {actual!s} does not match configured {expected.resolve()!s}"
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
    executable_allowlist: Mapping[str, Path] | None = None,
    effort_keys: Sequence[str] = DEFAULT_EFFORT_KEYS,
) -> Capability:
    """Run one override probe and classify it with the existing classifier.

    Classification is not reimplemented here. The observed value, its evidence
    kind, and the plan's parent value go straight to the existing classifier,
    which owns every rule that can withhold VERIFIED.

    Raises ProbeError when command does not implement plan: a different
    harness, or an invocation that does not carry the plan's child value.
    Both are refused before the CLI runs.
    """
    if command.harness != plan.harness:
        raise ProbeError(
            f"command targets {command.harness!r} but the plan probes {plan.harness!r}; "
            "a run against one harness cannot verify an override on another"
        )
    _validate_command(command, executable_allowlist=executable_allowlist)
    if not _carries_request(command, plan.child_value):
        raise ProbeError(
            f"command does not request {plan.child_value!r} in its argv, so an "
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
    executable_allowlist: Mapping[str, Path] | None = None,
) -> Capability:
    """Verify the harness launched a child in its backend event stream."""
    _validate_command(command, executable_allowlist=executable_allowlist)
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
    executable_allowlist: Mapping[str, Path] | None = None,
) -> Capability:
    """Measure the maximum children actually running at once."""
    if requested < 1:
        raise ProbeError("requested concurrency must be at least 1")
    _validate_command(command, executable_allowlist=executable_allowlist)
    if not _carries_request(command, str(requested)):
        raise ProbeError(
            f"command does not request concurrency {requested} in its typed request flag"
        )
    events, failure = _capture_events(command, runner=runner, timeout=timeout)
    if events is None:
        return Capability(CapabilityStatus.UNVERIFIED, EvidenceKind.NONE, failure)
    launches = subagent_launch_count(events)
    if launches < requested:
        return Capability(
            CapabilityStatus.UNVERIFIED,
            EvidenceKind.NONE,
            f"{command.harness} output recorded {launches} child launch attempts, "
            f"fewer than the requested {requested}",
        )
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


def _probe_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProbeError(f"{field} must be a non-empty string")
    return value


def _load_probe_command(
    value: Mapping[str, object],
    field: str,
    harness: str,
    *,
    request_value: str | int | None = None,
) -> ProbeCommand:
    raw_argv = value.get("argv")
    if (
        not isinstance(raw_argv, list)
        or not raw_argv
        or not all(isinstance(argument, str) and argument for argument in raw_argv)
    ):
        raise ProbeError(f"{field}.argv must be a non-empty string array")
    request_flag = value.get("request_flag")
    if request_flag is not None and (not isinstance(request_flag, str) or not request_flag):
        raise ProbeError(f"{field}.request_flag must be a non-empty string")
    if request_value is not None and request_flag is None:
        raise ProbeError(f"{field}.request_flag is required for this probe")
    if request_value is None and request_flag is not None:
        raise ProbeError(f"{field}.request_flag requires a typed probe request")
    cwd_value = value.get("cwd")
    if cwd_value is not None and not isinstance(cwd_value, str):
        raise ProbeError(f"{field}.cwd must be a string")
    env_value = value.get("env")
    if env_value is not None and (
        not isinstance(env_value, Mapping)
        or any(
            not isinstance(key, str) or not isinstance(item, str) for key, item in env_value.items()
        )
    ):
        raise ProbeError(f"{field}.env must map strings to strings")
    if any("\x00" in argument for argument in raw_argv):
        raise ProbeError(f"{field}.argv must not contain NUL bytes")
    if cwd_value is not None and "\x00" in cwd_value:
        raise ProbeError(f"{field}.cwd must not contain NUL bytes")
    if request_flag is not None and "\x00" in request_flag:
        raise ProbeError(f"{field}.request_flag must not contain NUL bytes")
    if env_value is not None and any(
        "\x00" in key or "\x00" in item for key, item in env_value.items()
    ):
        raise ProbeError(f"{field}.env must not contain NUL bytes")
    argv = tuple(raw_argv)
    if request_flag is not None:
        argv = (*argv, request_flag, str(request_value))
    command = ProbeCommand(
        harness=harness,
        argv=argv,
        cwd=Path(cwd_value) if cwd_value is not None else None,
        env=dict(env_value) if env_value is not None else None,
        request_flag=request_flag,
    )
    _validate_command(command)
    return command


def _load_probe_values(
    value: Mapping[str, object], field: str, capability: str
) -> tuple[str | None, str | None, int | None]:
    parent_value = value.get("parent_value")
    child_value = value.get("child_value")
    if capability in OVERRIDE_CAPABILITIES:
        parent_value = _probe_string(parent_value, f"{field}.parent_value")
        child_value = _probe_string(child_value, f"{field}.child_value")
    elif parent_value is not None or child_value is not None:
        raise ProbeError(f"{field} override values require an override capability")
    requested = value.get("requested")
    if capability == "concurrency_limit":
        if not isinstance(requested, int) or isinstance(requested, bool):
            raise ProbeError(f"{field}.requested must be an integer")
    elif requested is not None:
        raise ProbeError(f"{field}.requested requires concurrency_limit")

    return parent_value, child_value, requested


def _load_behavioral_probe(value: object, index: int) -> BehavioralProbe:
    field = f"probes[{index}]"
    if not isinstance(value, Mapping):
        raise ProbeError(f"{field} must be an object")
    allowed = {
        "harness",
        "capability",
        "argv",
        "cwd",
        "env",
        "request_flag",
        "parent_value",
        "child_value",
        "requested",
    }
    unknown = set(value) - allowed
    if unknown:
        raise ProbeError(f"{field} has unknown keys: {sorted(unknown)}")
    harness = _probe_string(value.get("harness"), f"{field}.harness")
    capability = _probe_string(value.get("capability"), f"{field}.capability")
    parent_value, child_value, requested = _load_probe_values(value, field, capability)
    if capability in OVERRIDE_CAPABILITIES or capability == "concurrency_limit":
        request_value = child_value if capability in OVERRIDE_CAPABILITIES else requested
        command = _load_probe_command(value, field, harness, request_value=request_value)
    else:
        if "request_flag" in value:
            raise ProbeError(f"{field}.request_flag requires an override or concurrency probe")
        command = _load_probe_command(value, field, harness)
    return BehavioralProbe(
        harness=harness,
        capability=capability,
        command=command,
        parent_value=parent_value,
        child_value=child_value,
        requested=requested,
    )


def load_behavioral_probes(path: Path) -> tuple[BehavioralProbe, ...]:
    """Load a fail-closed JSON plan for live behavioral probes."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProbeError(f"could not read behavioral probe plan: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ProbeError("behavioral probe plan must be an object")
    unknown = set(payload) - {"probes"}
    if unknown:
        raise ProbeError(f"behavioral probe plan has unknown keys: {sorted(unknown)}")
    raw_probes = payload.get("probes")
    if not isinstance(raw_probes, list) or not raw_probes:
        raise ProbeError("behavioral probe plan requires a non-empty probes array")
    probes = tuple(_load_behavioral_probe(value, index) for index, value in enumerate(raw_probes))
    keys = [(probe.harness, probe.capability) for probe in probes]
    if len(set(keys)) != len(keys):
        raise ProbeError("behavioral probe plan contains duplicate harness and capability entries")
    return probes
