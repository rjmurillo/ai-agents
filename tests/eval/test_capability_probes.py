"""Tests for the behavioral capability probers, issue #5423 step 2.

Every case here is deterministic: an injected fake runner returns recorded
runtime output, and no test touches the network, PATH, or a real CLI. No test
writes to `scripts/eval/examples/harness-capability-matrix.json`; the honesty
of that file is pinned by `test_harness_capability.py`.

Discrimination. Twenty-one mutations were run against `_capability_probes.py`,
each removing or weakening one guard, with `__pycache__` cleared between every
mutation and its rerun. All twenty-one were killed, a behavior-preserving
inverted control survived, and the restored file was byte-compared against the
original. Every case marked NEGATIVE CONTROL below failed under at least one of
those mutations and is named by it.

The nine cases marked CONFIRMATORY survived all twenty-one, or failed only as
collateral of a mutation aimed at a different case. They exercise a happy path,
or a path whose behavior belongs entirely to `_runtime_output`. They are here
because a reachable VERIFIED path is what gives the negative controls something
to be negative about, and they are labeled because they are not evidence that
any guard in this module works.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from tests.eval._harness_capability_test_support import capability, probes

CapabilityStatus = capability.CapabilityStatus
EvidenceKind = capability.EvidenceKind
HarnessCapabilityError = capability.HarnessCapabilityError
ProbeError = probes.ProbeError
ProbeCommand = probes.ProbeCommand

TIMEOUT = 5.0


def _jsonl(events: Sequence[Mapping[str, object]]) -> str:
    return "\n".join(json.dumps(event) for event in events) + "\n"


def _answer(text: str, **data: object) -> dict[str, object]:
    """One Copilot answer turn, the shape `copilot_result` already reads."""
    return {"type": "assistant.message", "data": {"content": text, **data}}


def _session_change(**data: object) -> dict[str, object]:
    """A session-state event: the CLI reporting its own configuration."""
    return {"type": "session.model_change", "data": dict(data)}


def _runner(
    stdout: str = "",
    *,
    returncode: int = 0,
    stderr: str = "",
    raises: BaseException | None = None,
    seen: list[list[str]] | None = None,
):
    """Build a fake runner that dispatches on argv rather than call order."""

    def run(argv: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if seen is not None:
            seen.append(list(argv))
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(list(argv), returncode, stdout, stderr)

    return run


def _command(harness: str = "copilot") -> probes.ProbeCommand:
    return ProbeCommand(harness=harness, argv=(harness, "--prompt", "probe"))


def _plan(
    *,
    capability_key: str = "model_override",
    harness: str = "copilot",
    parent: str = "claude-opus-5",
    candidates: Sequence[str] = ("gpt-5.6-sol",),
) -> probes.OverridePlan:
    return probes.build_override_plan(
        capability=capability_key,
        harness=harness,
        parent_value=parent,
        candidates=candidates,
    )


# --- Plan construction ---------------------------------------------------------


def test_a_plan_selects_the_first_candidate_that_differs_from_the_parent() -> None:
    """NEGATIVE CONTROL: an undiscriminating candidate must never be selected."""
    plan = _plan(candidates=("claude-opus-5", "gpt-5.6-sol"))

    assert plan.parent_value == "claude-opus-5"
    assert plan.child_value == "gpt-5.6-sol"


def test_an_equal_parent_and_child_value_cannot_produce_a_plan() -> None:
    """NEGATIVE CONTROL: the equal-value probe that can never verify anything."""
    with pytest.raises(ProbeError, match="cannot tell an honored override"):
        _plan(candidates=("claude-opus-5",))


def test_a_case_only_difference_cannot_produce_a_plan() -> None:
    """NEGATIVE CONTROL: a case-folding harness would echo the parent back."""
    with pytest.raises(ProbeError, match="cannot tell an honored override"):
        _plan(parent="Sol Ultra", candidates=("sol ultra", "  SOL ULTRA  "))


def test_sol_ultra_survives_plan_construction_unaliased() -> None:
    """NEGATIVE CONTROL: Sol Ultra is a literal, never folded onto a tier."""
    plan = _plan(
        capability_key="effort_override",
        parent="high",
        candidates=("Sol Ultra",),
    )

    assert plan.child_value == "Sol Ultra"
    assert plan.child_value not in {"high", "xhigh", "max"}


def test_sol_ultra_as_the_parent_still_admits_a_genuinely_different_child() -> None:
    """CONFIRMATORY: the guard rejects sameness, not the literal itself."""
    plan = _plan(capability_key="effort_override", parent="Sol Ultra", candidates=("high",))

    assert plan.parent_value == "Sol Ultra"
    assert plan.child_value == "high"


def test_a_plan_rejects_an_unknown_capability() -> None:
    """NEGATIVE CONTROL: only capabilities classify_override covers are probeable."""
    with pytest.raises(ProbeError, match="capability must be one of"):
        _plan(capability_key="concurrency_limit")


def test_a_plan_rejects_an_empty_parent_value() -> None:
    """NEGATIVE CONTROL: an unknown parent cannot discriminate."""
    with pytest.raises(ProbeError, match="parent_value must be"):
        _plan(parent="")


def test_a_plan_rejects_an_empty_harness() -> None:
    """NEGATIVE CONTROL: an unnamed harness cannot be recorded against."""
    with pytest.raises(ProbeError, match="harness must be"):
        _plan(harness="")


def test_a_plan_error_is_a_harness_capability_error() -> None:
    """CONFIRMATORY: callers keep one fail-closed except arm."""
    assert issubclass(ProbeError, HarnessCapabilityError)


# --- Model override probe ------------------------------------------------------


def test_a_backend_attributed_model_verifies_the_override() -> None:
    """CONFIRMATORY: the only path that may reach VERIFIED."""
    stdout = _jsonl([_session_change(newModel="gpt-5.6-sol"), _answer("hi", model="gpt-5.6-sol")])

    result = probes.probe_override(
        _plan(), _command(), runner=_runner(stdout), timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.VERIFIED
    assert result.evidence is EvidenceKind.BACKEND


def test_an_echo_only_output_never_verifies_the_override() -> None:
    """NEGATIVE CONTROL: client and schema echo is not backend evidence."""
    stdout = _jsonl([_session_change(newModel="gpt-5.6-sol"), _answer("hi")])

    result = probes.probe_override(
        _plan(), _command(), runner=_runner(stdout), timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.CLIENT_ECHO


def test_a_child_that_silently_inherits_the_parent_never_verifies() -> None:
    """NEGATIVE CONTROL: an inherit is not an honored override."""
    stdout = _jsonl([_answer("hi", model="claude-opus-5")])

    result = probes.probe_override(
        _plan(), _command(), runner=_runner(stdout), timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert "claude-opus-5" in result.detail


def test_a_hand_built_plan_with_an_equal_child_value_still_cannot_verify() -> None:
    """NEGATIVE CONTROL: the parent value reaches classify_override, not only the builder.

    `OverridePlan` is a public dataclass, so a caller can skip
    `build_override_plan`. Without the parent value forwarded, an equal-value
    plan whose backend echoes that value would read as a verified override.
    """
    plan = probes.OverridePlan(
        capability="model_override",
        harness="copilot",
        parent_value="gpt-5.6-sol",
        child_value="gpt-5.6-sol",
    )
    stdout = _jsonl([_answer("hi", model="gpt-5.6-sol")])

    result = probes.probe_override(plan, _command(), runner=_runner(stdout), timeout=TIMEOUT)

    assert result.status is CapabilityStatus.UNVERIFIED


def test_two_answer_turns_naming_different_models_verify_nothing() -> None:
    """NEGATIVE CONTROL: a blended answer has no single author."""
    stdout = _jsonl(
        [_answer("first", model="gpt-5.6-sol"), _answer("second", model="claude-opus-5")]
    )

    result = probes.probe_override(
        _plan(), _command(), runner=_runner(stdout), timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE


def test_a_harness_with_no_backend_model_parser_verifies_nothing() -> None:
    """NEGATIVE CONTROL: codex has no in-tree output parser, so it observes nothing."""
    stdout = _jsonl([_answer("hi", model="sol-medium")])

    result = probes.probe_override(
        _plan(harness="codex", parent="sol-low", candidates=("sol-medium",)),
        _command("codex"),
        runner=_runner(stdout),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE
    assert "no in-tree parser" in result.detail


def test_claude_init_model_is_not_treated_as_backend_evidence() -> None:
    """NEGATIVE CONTROL: the init event precedes any backend turn."""
    stdout = _jsonl(
        [
            {"type": "system", "subtype": "init", "model": "claude-opus-5"},
            {"type": "result", "result": "hi"},
        ]
    )

    result = probes.probe_override(
        _plan(harness="claude", parent="claude-sonnet-5", candidates=("claude-opus-5",)),
        _command("claude"),
        runner=_runner(stdout),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE


def test_the_probe_passes_the_command_argv_through_verbatim() -> None:
    """CONFIRMATORY: pins the injected-runner seam."""
    seen: list[list[str]] = []
    stdout = _jsonl([_answer("hi", model="gpt-5.6-sol")])

    probes.probe_override(
        _plan(), _command(), runner=_runner(stdout, seen=seen), timeout=TIMEOUT
    )

    assert seen == [["copilot", "--prompt", "probe"]]


# --- Effort override probe -----------------------------------------------------


def test_an_effort_on_an_answer_turn_verifies_the_override() -> None:
    """CONFIRMATORY: happy path for the effort observable."""
    stdout = _jsonl([_answer("hi", reasoningEffort="Sol Ultra")])

    result = probes.probe_override(
        _plan(capability_key="effort_override", parent="high", candidates=("Sol Ultra",)),
        _command(),
        runner=_runner(stdout),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.VERIFIED
    assert result.evidence is EvidenceKind.BACKEND
    assert "'Sol Ultra'" in result.detail


def test_an_effort_read_from_session_state_never_verifies() -> None:
    """NEGATIVE CONTROL: session state is the request echoed back."""
    stdout = _jsonl([_session_change(reasoningEffort="Sol Ultra"), _answer("hi")])

    result = probes.probe_override(
        _plan(capability_key="effort_override", parent="high", candidates=("Sol Ultra",)),
        _command(),
        runner=_runner(stdout),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.CLIENT_ECHO


def test_an_effort_on_a_contentless_turn_is_not_backend_evidence() -> None:
    """NEGATIVE CONTROL: a status line is not an answer the backend produced."""
    stdout = _jsonl([{"type": "assistant.message", "data": {"reasoningEffort": "Sol Ultra"}}])

    result = probes.probe_override(
        _plan(capability_key="effort_override", parent="high", candidates=("Sol Ultra",)),
        _command(),
        runner=_runner(stdout),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE


def test_an_effort_key_outside_the_configured_set_observes_nothing() -> None:
    """NEGATIVE CONTROL: the key set is a bounded allowlist, not a scan."""
    stdout = _jsonl([_answer("hi", tier="Sol Ultra")])

    result = probes.probe_override(
        _plan(capability_key="effort_override", parent="high", candidates=("Sol Ultra",)),
        _command(),
        runner=_runner(stdout),
        timeout=TIMEOUT,
    )

    assert result.evidence is EvidenceKind.NONE


def test_a_caller_supplied_effort_key_is_honored() -> None:
    """CONFIRMATORY: a live run can name the real key without a code change."""
    stdout = _jsonl([_answer("hi", tier="Sol Ultra")])

    result = probes.probe_override(
        _plan(capability_key="effort_override", parent="high", candidates=("Sol Ultra",)),
        _command(),
        runner=_runner(stdout),
        timeout=TIMEOUT,
        effort_keys=("tier",),
    )

    assert result.status is CapabilityStatus.VERIFIED


# --- Process-level failures ----------------------------------------------------


def test_a_missing_cli_yields_unverified_without_crashing() -> None:
    """NEGATIVE CONTROL: an absent PATH entry is a withheld claim, not a traceback."""
    runner = _runner(raises=FileNotFoundError(2, "No such file or directory", "copilot"))

    result = probes.probe_override(_plan(), _command(), runner=runner, timeout=TIMEOUT)

    assert result.status is CapabilityStatus.UNVERIFIED
    assert "is not on PATH" in result.detail


def test_a_timed_out_probe_yields_unverified() -> None:
    """NEGATIVE CONTROL: a killed run proves nothing about the capability."""
    runner = _runner(raises=subprocess.TimeoutExpired(cmd="copilot", timeout=TIMEOUT))

    result = probes.probe_override(_plan(), _command(), runner=runner, timeout=TIMEOUT)

    assert result.status is CapabilityStatus.UNVERIFIED
    assert "did not complete" in result.detail


def test_a_nonzero_exit_yields_unverified_and_records_stderr() -> None:
    """NEGATIVE CONTROL: a failed run is not a negative capability result."""
    runner = _runner("", returncode=1, stderr="not logged in")

    result = probes.probe_override(_plan(), _command(), runner=runner, timeout=TIMEOUT)

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.detail == "not logged in"


def test_malformed_runtime_output_fails_closed_rather_than_degrading() -> None:
    """NEGATIVE CONTROL: unparseable output raises, it does not become UNVERIFIED."""
    runner = _runner('{"type": "assistant.message"\n')

    with pytest.raises(HarnessCapabilityError, match="output is malformed"):
        probes.probe_override(_plan(), _command(), runner=runner, timeout=TIMEOUT)


def test_truncated_runtime_output_fails_closed() -> None:
    """NEGATIVE CONTROL: exit 0 with no events is a broken contract."""
    runner = _runner("   \n")

    with pytest.raises(HarnessCapabilityError, match="empty or truncated"):
        probes.probe_override(_plan(), _command(), runner=runner, timeout=TIMEOUT)


# --- Subagent support ----------------------------------------------------------


def test_subagent_events_in_the_stream_verify_support() -> None:
    """CONFIRMATORY: happy path; the observable comes from `traces`."""
    stdout = _jsonl(
        [{"type": "subagent.start", "data": {}}, {"type": "subagent.complete", "data": {}}]
    )

    result = probes.probe_subagent_support(_command(), runner=_runner(stdout), timeout=TIMEOUT)

    assert result.status is CapabilityStatus.VERIFIED
    assert result.evidence is EvidenceKind.BACKEND


def test_a_run_with_no_subagent_events_does_not_verify_support() -> None:
    """NEGATIVE CONTROL: asking for children is not observing them."""
    stdout = _jsonl([_answer("hi", model="gpt-5.6-sol")])

    result = probes.probe_subagent_support(_command(), runner=_runner(stdout), timeout=TIMEOUT)

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE


def test_a_missing_cli_does_not_crash_the_subagent_probe() -> None:
    """NEGATIVE CONTROL: same fail-closed path on a different prober."""
    runner = _runner(raises=FileNotFoundError(2, "No such file or directory", "codex"))

    result = probes.probe_subagent_support(
        _command("codex"), runner=runner, timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.UNVERIFIED


# --- Concurrency ---------------------------------------------------------------


def test_concurrency_records_the_observed_peak_not_the_requested_count() -> None:
    """NEGATIVE CONTROL: the config-echo failure applied to a count."""
    stdout = _jsonl(
        [
            {"type": "subagent.start", "data": {"id": "a"}},
            {"type": "subagent.start", "data": {"id": "b"}},
            {"type": "subagent.complete", "data": {"id": "a"}},
            {"type": "subagent.complete", "data": {"id": "b"}},
            {"type": "subagent.start", "data": {"id": "c"}},
            {"type": "subagent.complete", "data": {"id": "c"}},
        ]
    )

    result = probes.probe_concurrency(
        _command(), requested=4, runner=_runner(stdout), timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.VERIFIED
    assert result.value == 2
    assert result.value != 4


def test_starts_with_no_completion_boundary_cannot_derive_concurrency() -> None:
    """NEGATIVE CONTROL: N starts without ends is N sequential children too."""
    stdout = _jsonl(
        [{"type": "subagent.start", "data": {"id": str(index)}} for index in range(4)]
    )

    result = probes.probe_concurrency(
        _command(), requested=4, runner=_runner(stdout), timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.value is None


def test_claude_agent_tool_blocks_carry_no_concurrency_boundary() -> None:
    """CONFIRMATORY: no mutation of this module changes the result; `traces` owns it."""
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Task", "input": {}},
                    {"type": "tool_use", "name": "Task", "input": {}},
                ]
            },
        }
    ]

    assert probes.max_concurrent_children(events) is None


def test_a_sequential_run_records_a_peak_of_one() -> None:
    """CONFIRMATORY: pins the walk, which is arithmetic over the boundaries."""
    events = [
        {"type": "subagent.start"},
        {"type": "subagent.complete"},
        {"type": "subagent.start"},
        {"type": "subagent.complete"},
    ]

    assert probes.max_concurrent_children(events) == 1


def test_concurrency_rejects_a_requested_count_below_one() -> None:
    """NEGATIVE CONTROL: a probe that asks for no children measures nothing."""
    with pytest.raises(ProbeError, match="at least 1"):
        probes.probe_concurrency(
            _command(), requested=0, runner=_runner(""), timeout=TIMEOUT
        )


def test_a_missing_cli_does_not_crash_the_concurrency_probe() -> None:
    """NEGATIVE CONTROL: same fail-closed path on the third prober."""
    runner = _runner(raises=FileNotFoundError(2, "No such file or directory", "copilot"))

    result = probes.probe_concurrency(
        _command(), requested=2, runner=runner, timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.value is None
