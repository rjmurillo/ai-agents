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
    ProbeObservation,
    observe_copilot_effort,
    observe_copilot_model,
    observe_effort,
    observe_model,
)
from _capability_topology import (
    max_concurrent_children,
    requested_subagent_tools,
    subagent_launch_count,
    subagent_lifecycle_events,
)
from _codex_frames import (
    CodexFrame,
    CodexFrameError,
    ResponseSpan,
    parse_codex_frames,
)
from _codex_frames import (
    function_calls as codex_function_calls,
)
from _codex_frames import (
    peak_overlap as codex_peak_overlap,
)
from _codex_frames import (
    response_spans as codex_response_spans,
)
from _copilot_wire import (
    CopilotWireError,
    WireRequest,
    WireResponse,
    parse_wire_requests,
    parse_wire_responses,
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

#: Capabilities this module can probe through `classify_override`. `sol_ultra`
#: is a control value, not a fourth kind of evidence: it is probed exactly
#: like `effort_override` (`probe_override` routes every non-model capability
#: to `observe_effort`), and the request template it renders through is the
#: harness's effort template, because both requests land on the same CLI flag
#: (probed 2026-09-24: codex `-c model_reasoning_effort=<value>`, Copilot
#: `--reasoning-effort <value>`).
OVERRIDE_CAPABILITIES: tuple[str, ...] = ("model_override", "effort_override", "sol_ultra")


@dataclass(frozen=True, slots=True)
class _RequestTemplate:
    """One flag and value format a trusted override or concurrency probe may use.

    `value_format` is a `str.format` template applied to the caller's plain
    request value (`plan.child_value`, or `str(requested)` for concurrency)
    before it is compared against argv or rendered into a JSON-loaded plan's
    command. Codex's `-c` is a short GNU option: `codex exec --help` (codex-cli
    0.156.0, read 2026-09-24) documents it as `-c, --config <key=value>`, which
    does not accept `flag=value` syntax the way a long option does, so the key
    is folded into the single token that follows `-c` instead
    (`model_reasoning_effort=<value>`). Copilot's `--reasoning-effort` and
    `--model` are plain long options that take the value directly.
    """

    flag: str
    value_format: str = "{}"

    def render(self, value: str) -> str:
        return self.value_format.format(value)


# A JSON plan may choose the argv shape, but only these typed (flag,
# value_format) templates can carry behavioral probe requests for the
# supported harnesses, each pinned by a live `--help` read (codex-cli 0.156.0,
# Copilot CLI 1.0.89, both probed 2026-09-24). `codex`'s and `copilot`'s
# `effort_override` and `sol_ultra` rows share one template each: both
# requests render onto the same effort flag, and `_discriminates` is what
# tells "Sol Ultra" apart from a tier rather than the flag choice.
#
# Concurrency: codex caps concurrent child threads with `-c agents.max_threads=N`.
# It is enforced, and the root thread is not counted: with N=1 a second
# concurrent spawn failed with "collab spawn failed: agent thread limit reached"
# (tests/eval/fixtures/harness_capability/codex-0.156.0/thread-limit-1.trace.log,
# codex-cli 0.156.0, 2026-09-24). `copilot --help` (1.0.89) lists no concurrency
# option, so copilot has no entry, and `probe_concurrency` records UNVERIFIED
# "not trusted" rather than guessing a flag the CLI does not honor.
TRUSTED_REQUEST_TEMPLATES: Mapping[tuple[str, str], _RequestTemplate] = {
    ("codex", "model_override"): _RequestTemplate("--model"),
    ("codex", "effort_override"): _RequestTemplate("-c", "model_reasoning_effort={}"),
    ("codex", "sol_ultra"): _RequestTemplate("-c", "model_reasoning_effort={}"),
    ("codex", "concurrency_limit"): _RequestTemplate("-c", "agents.max_threads={}"),
    ("copilot", "model_override"): _RequestTemplate("--model"),
    ("copilot", "effort_override"): _RequestTemplate("--reasoning-effort"),
    ("copilot", "sol_ultra"): _RequestTemplate("--reasoning-effort"),
}


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


def _trusted_request_flag(command: ProbeCommand, capability: str) -> bool:
    template = TRUSTED_REQUEST_TEMPLATES.get((command.harness, capability))
    return template is not None and template.flag == command.request_flag


def _render_request_value(command: ProbeCommand, capability: str, value: str) -> str:
    """Return the request value as it would appear in argv for `capability`.

    Falls back to `value` unchanged when no template is trusted for this
    (harness, capability) pair, so an untrusted request flag still has a
    string to compare against; `_trusted_request_flag` is the single place
    that decides whether the probe is honored, not this function.
    """
    template = TRUSTED_REQUEST_TEMPLATES.get((command.harness, capability))
    return template.render(value) if template is not None else value


def _carries_request(command: ProbeCommand, value: str) -> bool:
    """Return whether the typed request flag is bound to the requested value.

    `value` must already be rendered through `_render_request_value`: for
    codex's `-c` template that is `model_reasoning_effort=<value>`, not the
    bare value, so a command carrying only the unformatted value after `-c`
    is correctly rejected here rather than misread as an honored request.

    Accepts the two-token form (`flag`, `value`) for any flag. Accepts the
    single-token `flag=value` form only for a long option (`--foo`): a short
    GNU option such as `-c` does not support `=` syntax (`codex exec --help`,
    codex-cli 0.156.0, read 2026-09-24), and codex's own rendered value
    already contains an `=` of its own, so a literal `-c=value` token must
    never satisfy this check.
    """
    flag = command.request_flag
    if flag is None:
        return False
    two_token = any(
        token == flag and index + 1 < len(command.argv) and command.argv[index + 1] == value
        for index, token in enumerate(command.argv)
    )
    if two_token:
        return True
    if not flag.startswith("--"):
        return False
    return f"{flag}={value}" in command.argv


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


#: Longest failure reason carried into a matrix cell. A codex run under
#: `RUST_LOG=tungstenite::protocol=trace` writes megabytes of stderr, so the
#: whole stream would bury the one line that explains the exit.
MAX_FAILURE_REASON = 500

#: Event types whose message explains a failed run. Copilot CLI 1.0.89 exits 1
#: with empty stderr and reports quota and auth failures only as a
#: `session.error` event on stdout; codex reports `turn.failed` and `error`
#: (both probed 2026-09-24).
_FAILURE_EVENTS: frozenset[str] = frozenset({"session.error", "turn.failed", "error"})


def _stdout_failure(stdout: str) -> str:
    """Return the last failure message a runtime wrote to its event stream."""
    message = ""
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") not in _FAILURE_EVENTS:
            continue
        data = event.get("data") or event.get("error") or event
        text = data.get("message") if isinstance(data, dict) else None
        if isinstance(text, str) and text:
            message = text
    return message


def _failure_reason(harness: str, returncode: int, stdout: str | None, stderr: str) -> str:
    """Name why a probe failed in one bounded line, never the whole stream."""
    reason = _stdout_failure(stdout or "")
    if not reason:
        # A clap usage error puts the reason on its `error:` line and ends
        # with a "try '--help'" hint, so the error line wins over the last.
        lines = [line.strip() for line in stderr.splitlines() if line.strip()]
        errors = [line for line in lines if line.lower().startswith("error")]
        reason = (errors or lines or [""])[-1]
    if not reason:
        return f"{harness} probe exited with code {returncode}"
    return f"{harness} probe exited with code {returncode}: {reason[:MAX_FAILURE_REASON]}"


def _run_probe(
    command: ProbeCommand,
    *,
    runner: Runner,
    timeout: float,
) -> tuple[subprocess.CompletedProcess[str] | None, str]:
    """Run one probe with stdin closed, or return why it could not run."""
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
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        return None, f"{command.argv[0]} is not on PATH: {exc}"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{command.harness} probe did not complete: {exc}"
    return run, ""


def _capture_events(
    command: ProbeCommand,
    *,
    runner: Runner,
    timeout: float,
) -> tuple[list[dict[str, object]] | None, str, str]:
    """Run one probe and return its events, a failure reason, and raw stderr.

    A missing CLI, a failed launch, a timeout, and a non-zero exit return
    `(None, reason, stderr)` so the caller records `UNVERIFIED`. Malformed or
    empty output raises, because output that cannot be parsed says nothing
    about the capability and must not be read as a negative result either.

    `stdin=subprocess.DEVNULL` closes stdin for the child process. Codex reads
    from stdin when none is provided (`codex exec` prints "Reading additional
    input from stdin..." and blocks on it, probed 2026-09-24, codex-cli
    0.156.0), which would hang a probe indefinitely rather than exit within
    `timeout`.

    `stderr` is returned even on success (empty string on the exception paths,
    where no process ran): codex carries no model or reasoning effort in its
    `--json` stdout event stream at all (probed 2026-09-24), so
    `_capability_evidence.observe_model`/`observe_effort` read codex's backend
    evidence from this stderr instead, when the caller ran it with
    `RUST_LOG=tungstenite::protocol=trace`.
    """
    run, failure = _run_probe(command, runner=runner, timeout=timeout)
    if run is None:
        return None, failure, ""
    stderr = run.stderr or ""
    if run.returncode != 0:
        return None, _failure_reason(command.harness, run.returncode, run.stdout, stderr), stderr
    try:
        events = parse_events(run.stdout or "")
    except RuntimeOutputError as exc:
        raise ProbeError(f"{command.harness} probe output is malformed: {exc}") from exc
    if not events:
        raise ProbeError(
            f"{command.harness} probe exited 0 with no events; the output is empty or truncated"
        )
    return events, "", stderr


def _capture_codex_frames(
    command: ProbeCommand,
    *,
    runner: Runner,
    timeout: float,
) -> tuple[tuple[CodexFrame, ...] | None, str]:
    """Run one codex probe and return its backend frames, or a reason it produced none.

    Codex's `--json` stdout carries no model or effort at all (see
    `_codex_frames`'s module docstring); backend evidence exists only on
    stderr, and only when the caller set
    `RUST_LOG=tungstenite::protocol=trace`. A missing CLI, a failed launch, a
    timeout, and a non-zero exit return `(None, reason)`, mirroring
    `_capture_events`, so the caller records `UNVERIFIED`. Exit 0 with no
    frames on stderr also returns `(None, reason)`, naming the missing
    `RUST_LOG=tungstenite::protocol=trace`, the contract PR #5910 set for
    codex override probes.
    """
    run, failure = _run_probe(command, runner=runner, timeout=timeout)
    if run is None:
        return None, failure
    stderr = run.stderr or ""
    if run.returncode != 0:
        return None, _failure_reason(command.harness, run.returncode, run.stdout, stderr)
    try:
        frames = parse_codex_frames(stderr)
    except CodexFrameError as exc:
        raise ProbeError(f"{command.harness} probe stderr is malformed: {exc}") from exc
    if not frames:
        return None, (
            f"{command.harness} stderr carried no backend frame; rerun with "
            "RUST_LOG=tungstenite::protocol=trace to capture the backend Response object"
        )
    return tuple(frames), ""


def _find_flag_value(argv: Sequence[str], flag: str) -> str | None:
    try:
        index = argv.index(flag)
    except ValueError:
        return None
    return argv[index + 1] if index + 1 < len(argv) else None


def _newest_log_file(log_path: Path) -> Path | None:
    """Return the most recently modified `process-*.log` under `log_path`.

    A run's `--log-dir` can accumulate one file per invocation across a
    reused directory; joining all of them would mix an earlier run's wire
    evidence into this one's, so only the newest by mtime is read.
    """
    if not log_path.is_dir():
        return None
    log_files = list(log_path.glob("process-*.log"))
    if not log_files:
        return None
    return max(log_files, key=lambda path: path.stat().st_mtime)


def _capture_copilot_wire(
    command: ProbeCommand,
    *,
    runner: Runner,
    timeout: float,
) -> tuple[list[dict[str, object]] | None, tuple[WireResponse, ...], tuple[WireRequest, ...], str]:
    """Run one copilot probe and return its events plus its backend wire evidence.

    `assistant.message.data.model` is a client label, not backend evidence
    (see `_capability_evidence.observe_copilot_model`), so a model or effort
    override probe additionally needs the debug log `--log-level all
    --log-dir <dir>` writes. This function does not add that flag; it reads
    whichever `--log-dir` value is already in `command.argv`, and returns a
    reason naming the missing flag when the caller's plan omitted it or the
    log carried no wire responses, rather than silently falling back to
    client-echoed evidence.
    """
    events, failure, _stderr = _capture_events(command, runner=runner, timeout=timeout)
    if events is None:
        return None, (), (), failure
    log_dir = _find_flag_value(command.argv, "--log-dir")
    if log_dir is None:
        return (
            events,
            (),
            (),
            "no --log-dir in the command argv; pass --log-level all --log-dir "
            "<dir> to capture backend wire evidence",
        )
    log_file = _newest_log_file(Path(log_dir))
    if log_file is None:
        return (
            events,
            (),
            (),
            f"no process-*.log file under {log_dir}; pass --log-level all "
            "--log-dir <dir> to capture backend wire evidence",
        )
    text = log_file.read_text(encoding="utf-8")
    try:
        responses = tuple(parse_wire_responses(text))
        requests = tuple(parse_wire_requests(text))
    except CopilotWireError as exc:
        raise ProbeError(f"{command.harness} wire log is malformed: {exc}") from exc
    if not responses:
        return (
            events,
            (),
            requests,
            f"{log_dir} carried no backend wire responses; pass --log-level all "
            "--log-dir <dir> to capture them",
        )
    return events, responses, requests, ""


def _observe_copilot_override(
    plan: OverridePlan, command: ProbeCommand, *, runner: Runner, timeout: float
) -> ProbeObservation | Capability:
    """Read copilot override evidence from its wire log, or a capture-failure `Capability`."""
    events, responses, requests, failure = _capture_copilot_wire(
        command, runner=runner, timeout=timeout
    )
    if events is None:
        return Capability(CapabilityStatus.UNVERIFIED, EvidenceKind.NONE, failure)
    if plan.capability == "model_override":
        if not responses:
            return Capability(CapabilityStatus.UNVERIFIED, EvidenceKind.NONE, failure)
        return observe_copilot_model(events, responses)
    if not requests:
        return Capability(CapabilityStatus.UNVERIFIED, EvidenceKind.NONE, failure)
    return observe_copilot_effort(requests)


def _observe_generic_override(
    plan: OverridePlan,
    command: ProbeCommand,
    *,
    runner: Runner,
    timeout: float,
    effort_keys: Sequence[str],
) -> ProbeObservation | Capability:
    """Read override evidence from `--json` stdout events and codex trace stderr."""
    events, failure, stderr = _capture_events(command, runner=runner, timeout=timeout)
    if events is None:
        return Capability(CapabilityStatus.UNVERIFIED, EvidenceKind.NONE, failure)
    if plan.capability == "model_override":
        return observe_model(plan.harness, events, stderr=stderr)
    return observe_effort(plan.harness, events, effort_keys=effort_keys, stderr=stderr)


def _guard_override_plan(
    plan: OverridePlan,
    command: ProbeCommand,
    *,
    executable_allowlist: Mapping[str, Path] | None,
) -> Capability | None:
    """Refuse a command that cannot implement `plan`, or an untrusted flag.

    Raises `ProbeError` for a harness mismatch or an argv that does not
    carry the plan's child value, both before any CLI runs. Returns the
    `UNVERIFIED`/"not trusted" `Capability` for an untrusted request flag,
    or `None` once `plan` and `command` have cleared every guard and the
    caller may proceed to capture evidence.
    """
    if command.harness != plan.harness:
        raise ProbeError(
            f"command targets {command.harness!r} but the plan probes {plan.harness!r}; "
            "a run against one harness cannot verify an override on another"
        )
    _validate_command(command, executable_allowlist=executable_allowlist)
    rendered_child = _render_request_value(command, plan.capability, plan.child_value)
    if not _carries_request(command, rendered_child):
        raise ProbeError(
            f"command does not request {plan.child_value!r} in its argv, so an "
            f"observed {plan.child_value!r} would be the harness default rather than an "
            "honored override"
        )
    if not _trusted_request_flag(command, plan.capability):
        return Capability(
            CapabilityStatus.UNVERIFIED,
            EvidenceKind.NONE,
            f"{command.harness} request flag {command.request_flag!r} is not trusted "
            f"for {plan.capability}",
        )
    return None


def _observe_override(
    plan: OverridePlan,
    command: ProbeCommand,
    *,
    runner: Runner,
    timeout: float,
    effort_keys: Sequence[str],
) -> ProbeObservation | Capability:
    """Route to the evidence reader for `plan.harness`.

    Copilot reads its `--log-dir` wire log. Every other harness reads
    `--json` stdout events, and codex additionally reads its agreeing
    `response.completed` frames from `RUST_LOG` trace stderr.
    """
    if plan.harness == "copilot":
        return _observe_copilot_override(plan, command, runner=runner, timeout=timeout)
    return _observe_generic_override(
        plan, command, runner=runner, timeout=timeout, effort_keys=effort_keys
    )


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

    Classification is not reimplemented here: the observed value, its
    evidence kind, and the plan's parent value go straight to the existing
    classifier, which owns every rule that can withhold `VERIFIED`. Guard
    checks live in `_guard_override_plan`, and reading the evidence lives
    in `_observe_override`.
    """
    rejection = _guard_override_plan(plan, command, executable_allowlist=executable_allowlist)
    if rejection is not None:
        return rejection
    result = _observe_override(
        plan, command, runner=runner, timeout=timeout, effort_keys=effort_keys
    )
    if isinstance(result, Capability):
        return result
    status = classify_override(
        plan.child_value, result.observed, result.evidence, parent_value=plan.parent_value
    )
    return Capability(
        status=status,
        evidence=result.evidence,
        detail=(
            f"requested {plan.child_value!r} against parent {plan.parent_value!r}; "
            f"observed {result.observed!r} ({result.detail})"
        ),
    )


def _codex_spawn_models(frames: Sequence[CodexFrame]) -> list[str]:
    """Return every model a `spawn_agent` call in `frames` explicitly named.

    A `spawn_agent` call with no `model` argument (a child that inherits the
    parent's model, as in `codex-0.156.0/reviewer-isolation.trace.log`)
    contributes nothing: it cannot discriminate a launched child from the
    parent's own continuation turns, which is exactly what
    `probe_subagent_support` and `probe_concurrency` need to rule out.
    """
    models: list[str] = []
    for name, arguments in codex_function_calls(frames):
        if name != "spawn_agent":
            continue
        model = arguments.get("model")
        if isinstance(model, str) and model:
            models.append(model)
    return models


def _codex_spawn_call_indices(frames: Sequence[CodexFrame]) -> list[int]:
    """Return the frame position of every `spawn_agent` function-call frame."""
    indices: list[int] = []
    for index, frame in enumerate(frames):
        payload = frame.payload
        if payload.get("type") != "response.output_item.done":
            continue
        item = payload.get("item")
        if (
            isinstance(item, Mapping)
            and item.get("type") == "function_call"
            and item.get("name") == "spawn_agent"
        ):
            indices.append(index)
    return indices


def _codex_parent_signature(spans: Sequence[ResponseSpan]) -> tuple[str, str | None] | None:
    """Return the first span's `(model, effort)`, the parent's own signature."""
    if not spans:
        return None
    return (spans[0].model, spans[0].effort)


def _codex_child_spans(frames: Sequence[CodexFrame]) -> list[ResponseSpan]:
    """Return spans that plausibly answer for a spawned child, not the parent.

    A span counts only when both hold (issue #5423 review finding 5):
    it was created after at least one `spawn_agent` call frame, and its
    `(model, effort)` differs from the parent's own (the first span's).
    Neither check alone is enough: a `spawn_agent` call that names the
    parent's own model, or that fails outright (`collab spawn failed`),
    must not be read as a verified child merely because the parent's own
    completed spans happen to share that model, and a span with a genuinely
    different model that somehow preceded any spawn request is not a
    spawned child either.
    """
    spans = codex_response_spans(frames)
    parent = _codex_parent_signature(spans)
    if parent is None:
        return []
    spawn_indices = _codex_spawn_call_indices(frames)
    if not spawn_indices:
        return []
    earliest_spawn = min(spawn_indices)
    return [
        span
        for span in spans
        if span.created > earliest_spawn and (span.model, span.effort) != parent
    ]


def _codex_subagent_support(command: ProbeCommand, frames: Sequence[CodexFrame]) -> Capability:
    """Verify codex launched a child that differs from the parent and completed.

    Codex never emits the `subagent.*` event vocabulary
    `_capability_topology` reads, so `subagent_support` is read from
    `_codex_child_spans` instead (see its docstring for the exact rule).
    Verified against `codex-0.156.0/subagent-luna-high.trace.log`, whose
    three child spans (`gpt-6-luna`/`high`) complete after the parent's
    (`gpt-5.6-sol`/`medium`) `spawn_agent` calls.
    """
    completed_children = [span for span in _codex_child_spans(frames) if span.completed is not None]
    if not completed_children:
        return Capability(
            CapabilityStatus.UNVERIFIED,
            EvidenceKind.NONE,
            f"{command.harness} output carried no completed child response that differs "
            "from the parent's own (model, effort) and followed a spawn_agent call",
        )
    return Capability(
        CapabilityStatus.VERIFIED,
        EvidenceKind.BACKEND,
        f"{command.harness} output carried a completed child response on model "
        f"{completed_children[0].model!r}, differing from the parent and following a "
        "spawn_agent call",
    )


def _copilot_subagent_support(
    command: ProbeCommand, *, runner: Runner, timeout: float
) -> Capability:
    """Verify a copilot child from its provider response, not its lifecycle events.

    `subagent.started` and `subagent.completed` are client events, so they
    alone earn only `CLIENT_ECHO`. `VERIFIED` needs a wire-log response on a
    model some `subagent.started` event requested, and that model must differ
    from the parent's first response model, so the response is attributable
    to the child rather than to the parent.
    """
    events, responses, _requests, failure = _capture_copilot_wire(
        command, runner=runner, timeout=timeout
    )
    if events is None:
        return Capability(CapabilityStatus.UNVERIFIED, EvidenceKind.NONE, failure)
    launched = subagent_lifecycle_events(events)
    if not launched:
        return Capability(
            CapabilityStatus.UNVERIFIED,
            EvidenceKind.NONE,
            "copilot output carried no subagent events",
        )
    child_models = {
        data.get("model")
        for event in events
        if event.get("type") == "subagent.started"
        and isinstance(data := event.get("data"), Mapping)
    }
    parent_model = responses[0].model if responses else None
    attributed = sorted(
        {r.model for r in responses if r.model in child_models and r.model != parent_model}
    )
    if not attributed:
        return Capability(
            CapabilityStatus.UNVERIFIED,
            EvidenceKind.CLIENT_ECHO,
            f"copilot output carried {len(launched)} client subagent lifecycle events but no "
            "wire response attributable to a child model; "
            + (failure or "request a child model that differs from the parent's"),
        )
    return Capability(
        CapabilityStatus.VERIFIED,
        EvidenceKind.BACKEND,
        f"copilot wire log carried a provider response on child model {attributed[0]!r}, "
        f"distinct from the parent's {parent_model!r}",
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
    if command.harness == "codex":
        frames, failure = _capture_codex_frames(command, runner=runner, timeout=timeout)
        if frames is None:
            return Capability(CapabilityStatus.UNVERIFIED, EvidenceKind.NONE, failure)
        return _codex_subagent_support(command, frames)
    if command.harness == "copilot":
        return _copilot_subagent_support(command, runner=runner, timeout=timeout)
    events, failure, _stderr = _capture_events(command, runner=runner, timeout=timeout)
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


def _codex_concurrency(
    command: ProbeCommand, frames: Sequence[CodexFrame], *, requested: int
) -> Capability:
    """Measure the peak concurrent codex children on the requested child model.

    `peak_overlap` runs over `_codex_child_spans` only, never the full span
    list: excluding the parent's own spans (issue #5423 review finding 5)
    means a parent that happens to share the requested child model can
    never inflate the count. Verified against
    `codex-0.156.0/concurrency-3-requested.trace.log`: four `spawn_agent`
    calls name `gpt-6-luna` (the first, with `fork_turns=all`, failed under
    `--ephemeral` and was retried), and at most two of that model's child spans
    overlap, so a request for three stays `UNVERIFIED` with `value=2`,
    matching this repository's checked-in matrix.
    """
    requested_models = _codex_spawn_models(frames)
    if len(requested_models) < requested:
        return Capability(
            CapabilityStatus.UNVERIFIED,
            EvidenceKind.NONE,
            f"{command.harness} output recorded {len(requested_models)} spawn_agent call(s) "
            f"naming a model, fewer than the requested {requested}",
        )
    target_model = requested_models[0]
    child_spans = _codex_child_spans(frames)
    peak = codex_peak_overlap(child_spans, model=target_model)
    if peak is None:
        return Capability(
            CapabilityStatus.UNVERIFIED,
            EvidenceKind.NONE,
            f"{command.harness} output has no completed child response on {target_model!r}, "
            f"so concurrency cannot be derived (requested {requested})",
        )
    status = CapabilityStatus.VERIFIED if peak >= requested else CapabilityStatus.UNVERIFIED
    return Capability(
        status,
        EvidenceKind.BACKEND,
        f"{command.harness} ran at most {peak} children of {target_model!r} at once while "
        f"{requested} were requested",
        value=peak,
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
    rendered_requested = _render_request_value(command, "concurrency_limit", str(requested))
    if not _carries_request(command, rendered_requested):
        raise ProbeError(
            f"command does not request concurrency {requested} in its typed request flag"
        )
    if not _trusted_request_flag(command, "concurrency_limit"):
        return Capability(
            CapabilityStatus.UNVERIFIED,
            EvidenceKind.NONE,
            f"{command.harness} request flag {command.request_flag!r} is not trusted "
            "for concurrency_limit",
        )
    if command.harness == "codex":
        frames, failure = _capture_codex_frames(command, runner=runner, timeout=timeout)
        if frames is None:
            return Capability(CapabilityStatus.UNVERIFIED, EvidenceKind.NONE, failure)
        return _codex_concurrency(command, frames, requested=requested)
    events, failure, _stderr = _capture_events(command, runner=runner, timeout=timeout)
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
    status = CapabilityStatus.VERIFIED if peak >= requested else CapabilityStatus.UNVERIFIED
    return Capability(
        status,
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
    capability: str,
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
        template = TRUSTED_REQUEST_TEMPLATES.get((harness, capability))
        raw_value = str(request_value)
        rendered = template.render(raw_value) if template is not None else raw_value
        argv = (*argv, request_flag, rendered)
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
        command = _load_probe_command(
            value, field, harness, capability, request_value=request_value
        )
    else:
        if "request_flag" in value:
            raise ProbeError(f"{field}.request_flag requires an override or concurrency probe")
        command = _load_probe_command(value, field, harness, capability)
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
