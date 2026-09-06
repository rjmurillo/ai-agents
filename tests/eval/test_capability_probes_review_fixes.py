"""Tests for the review findings on PR #5623, issue #5423 step 2.

The Devin review landed five seconds after that PR merged, so these cases
cover fixes made after the fact rather than changes to unshipped code. Four
findings are behavioral and covered here: a probe command that does not
implement its plan, a hand-built plan that differs from its parent only by
case or whitespace, a subagent tool request counted as a launch, and a
concurrency peak counted from starts no completion can close.

Every case in this module was run against the pre-fix code at `aa951a0` and
failed there, so each is a negative control for the guard it names rather
than a restatement of behavior that already held. The three marked
CONFIRMATORY are the passing halves of a pair and are labeled because they
are not evidence that any guard works.
"""

from __future__ import annotations

import pytest

from tests.eval._capability_probe_fixtures import (
    TIMEOUT,
    CapabilityStatus,
    EvidenceKind,
    ProbeError,
    _answer,
    _command,
    _jsonl,
    _plan,
    _runner,
)
from tests.eval._harness_capability_test_support import probes, topology

# A stream that would verify the model override if the command were bound to
# the plan. Reused so each case below differs only in the command.
_HONORED = _jsonl([_answer("hi", model="gpt-5.6-sol")])


# --- The command must implement the plan (Devin BUG_0001) ----------------------


def test_a_command_that_never_requests_the_override_is_refused() -> None:
    """NEGATIVE CONTROL: an unbound argv makes the harness default read as an override."""
    seen: list[list[str]] = []

    with pytest.raises(ProbeError, match="does not request"):
        probes.probe_override(
            _plan(),
            _command(requests=None),
            runner=_runner(_HONORED, seen=seen),
            timeout=TIMEOUT,
        )

    assert seen == [], "the CLI must not run before the command is bound to the plan"


def test_a_command_requesting_a_different_value_is_refused() -> None:
    """NEGATIVE CONTROL: a changed request is as unbound as a missing one."""
    with pytest.raises(ProbeError, match="does not request"):
        probes.probe_override(
            _plan(),
            _command(requests="claude-sonnet-5"),
            runner=_runner(_HONORED),
            timeout=TIMEOUT,
        )


def test_a_command_targeting_another_harness_is_refused() -> None:
    """NEGATIVE CONTROL: a run against copilot cannot verify a codex override."""
    seen: list[list[str]] = []

    with pytest.raises(ProbeError, match="but the plan probes"):
        probes.probe_override(
            _plan(harness="codex", parent="sol-low", candidates=("gpt-5.6-sol",)),
            _command("copilot"),
            runner=_runner(_HONORED, seen=seen),
            timeout=TIMEOUT,
        )

    assert seen == [], "the CLI must not run for a harness the plan does not probe"


def test_an_equals_joined_flag_carries_the_request() -> None:
    """CONFIRMATORY: `--model=value` is the same request as `--model value`."""
    command = probes.ProbeCommand(
        harness="copilot", argv=("copilot", "--model=gpt-5.6-sol")
    )

    result = probes.probe_override(
        _plan(), command, runner=_runner(_HONORED), timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.VERIFIED


def test_an_environment_value_no_longer_carries_the_request() -> None:
    """NEGATIVE CONTROL: any variable whose value matched counted as the request.

    The env surface accepted a match from any variable, so one that happened
    to hold the model string bound a command that never asked for it. Naming
    the variables that really carry the request would mean writing down a
    Codex and Copilot contract this repository has not verified, so argv is
    the only surface now.
    """
    command = probes.ProbeCommand(
        harness="copilot",
        argv=("copilot", "--prompt", "probe"),
        env={"UNRELATED_CACHE_KEY": "gpt-5.6-sol"},
    )

    with pytest.raises(ProbeError, match="does not request"):
        probes.probe_override(_plan(), command, runner=_runner(_HONORED), timeout=TIMEOUT)


def test_a_command_whose_executable_does_not_name_the_harness_is_refused() -> None:
    """NEGATIVE CONTROL: the harness field is a label, not evidence of the process."""
    seen: list[list[str]] = []
    command = probes.ProbeCommand(
        harness="copilot", argv=("codex", "--model", "gpt-5.6-sol")
    )

    with pytest.raises(ProbeError, match="does not name"):
        probes.probe_override(
            _plan(), command, runner=_runner(_HONORED, seen=seen), timeout=TIMEOUT
        )

    assert seen == [], "the CLI must not run when the label and the executable disagree"


def test_an_executable_path_still_satisfies_the_harness_check() -> None:
    """CONFIRMATORY: an absolute path to the CLI is the normal shape, not a violation."""
    command = probes.ProbeCommand(
        harness="copilot", argv=("/usr/local/bin/copilot", "--model", "gpt-5.6-sol")
    )

    result = probes.probe_override(
        _plan(), command, runner=_runner(_HONORED), timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.VERIFIED


def test_a_hand_built_plan_naming_an_unprobeable_capability_is_refused() -> None:
    """NEGATIVE CONTROL: probe_override routes every non-model capability to effort.

    The capability check lived only in `build_override_plan`, so a hand-built
    plan naming anything else had effort evidence classified as that
    capability.
    """
    with pytest.raises(ProbeError, match="capability must be one of"):
        probes.OverridePlan(
            capability="concurrency_limit",
            harness="copilot",
            parent_value="2",
            child_value="4",
        )


# --- A tool request is not a launched child (Devin BUG_0004) -------------------


def _claude_tool_use(count: int = 1) -> list[dict[str, object]]:
    return [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Task", "input": {}} for _ in range(count)
                ]
            },
        }
    ]


def test_a_claude_tool_request_alone_does_not_verify_subagent_support() -> None:
    """NEGATIVE CONTROL: `traces` merges asks with launches; support needs a launch."""
    result = probes.probe_subagent_support(
        _command("claude"), runner=_runner(_jsonl(_claude_tool_use(2))), timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE
    assert "2 subagent tool requests" in result.detail


def test_a_request_paired_with_a_lifecycle_event_verifies_support() -> None:
    """CONFIRMATORY: the ask stops mattering once the runtime reports a child."""
    events = _claude_tool_use() + [{"type": "subagent.start", "data": {}}]

    result = probes.probe_subagent_support(
        _command("claude"), runner=_runner(_jsonl(events)), timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.VERIFIED
    assert result.detail.endswith("1 subagent lifecycle events")


# --- A peak needs completions to close it (Devin BUG_0002) --------------------


def _boundaries(*kinds: str) -> list[dict[str, object]]:
    return [{"type": f"subagent.{kind}"} for kind in kinds]


def test_a_completed_pair_then_unclosed_starts_measures_nothing() -> None:
    """NEGATIVE CONTROL: this published one while three children were still open.

    The first fix called that lower bound conservative. For a maximum it is
    not: the same stream shows four starts, so reporting one as the verified
    maximum claims a limit below a number of children the evidence already
    shows running.
    """
    events = _boundaries("start", "complete", "start", "start", "start")

    assert topology.max_concurrent_children(events) is None


def test_a_truncated_stream_measures_nothing() -> None:
    """NEGATIVE CONTROL: a stream that ends mid-run has not shown its maximum."""
    events = _boundaries("start", "start", "complete")

    assert topology.max_concurrent_children(events) is None


def test_a_completion_with_no_child_open_derives_no_concurrency() -> None:
    """NEGATIVE CONTROL: boundaries that cannot describe a run measure nothing.

    The input has to end balanced to observe this guard at all. A stream that
    merely opens with a completion, `complete, start`, ends one child deep, so
    the end-of-stream check rejects it whether or not the unmatched-completion
    branch exists, and a test built on that input passes against code with the
    branch removed. This stream closes level, so only the branch under test
    can reject it: without it the extra completion is absorbed and a peak of
    one is published for an incoherent run.
    """
    events = _boundaries("start", "complete", "complete", "start", "complete")

    assert topology.max_concurrent_children(events) is None


def test_a_fully_paired_overlap_still_reports_its_real_peak() -> None:
    """CONFIRMATORY: the guard lowers unclosed peaks, not closed ones."""
    events = _boundaries("start", "start", "start", "complete", "complete", "complete")

    assert topology.max_concurrent_children(events) == 3


def test_an_inflated_stream_leaves_the_concurrency_probe_unverified() -> None:
    """NEGATIVE CONTROL: the count guard reaches the prober, not only the helper."""
    stdout = _jsonl(_boundaries("start", "start", "start"))

    result = probes.probe_concurrency(
        _command(), requested=3, runner=_runner(stdout), timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.value is None
