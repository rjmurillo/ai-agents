"""Subagent and concurrency probe tests, split from test_capability_probes.py.

Same fake runner and recorded runtime output as that file. No network, no
PATH lookup, and no real CLI.
"""

from __future__ import annotations

import pytest

from tests.eval._capability_probe_fixtures import (
    TIMEOUT,
    CapabilityStatus,
    EvidenceKind,
    ProbeCommand,
    ProbeError,
    _answer,
    _command,
    _jsonl,
    _runner,
    codex_message_line,
    codex_spawn_agent_line,
    codex_stderr,
)
from tests.eval._harness_capability_test_support import FIXTURES, probes, topology

# --- Subagent support ----------------------------------------------------------


def test_subagent_events_in_the_stream_verify_support() -> None:
    """CONFIRMATORY: happy path; the observable comes from `traces`."""
    stdout = _jsonl(
        [{"type": "subagent.start", "data": {}}, {"type": "subagent.complete", "data": {}}]
    )

    result = probes.probe_subagent_support(
        _command("claude"), runner=_runner(stdout), timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.VERIFIED
    assert result.evidence is EvidenceKind.BACKEND


def test_copilot_lifecycle_events_without_a_wire_log_never_verify() -> None:
    """NEGATIVE CONTROL: copilot `subagent.*` events are client-emitted."""
    stdout = _jsonl(
        [
            {"type": "subagent.started", "data": {"model": "claude-sonnet-4-6"}},
            {"type": "subagent.completed", "data": {"model": "claude-sonnet-4-6"}},
        ]
    )

    result = probes.probe_subagent_support(_command(), runner=_runner(stdout), timeout=TIMEOUT)

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.CLIENT_ECHO


def test_a_run_with_no_subagent_events_does_not_verify_support() -> None:
    """NEGATIVE CONTROL: asking for children is not observing them."""
    stdout = _jsonl([_answer("hi", model="gpt-5.6-sol")])

    result = probes.probe_subagent_support(_command(), runner=_runner(stdout), timeout=TIMEOUT)

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE


def test_a_missing_cli_does_not_crash_the_subagent_probe() -> None:
    """NEGATIVE CONTROL: same fail-closed path on a different prober."""
    runner = _runner(raises=FileNotFoundError(2, "No such file or directory", "codex"))

    result = probes.probe_subagent_support(_command("codex"), runner=runner, timeout=TIMEOUT)

    assert result.status is CapabilityStatus.UNVERIFIED


def test_a_parent_on_the_child_model_with_a_failed_spawn_never_verifies_support() -> None:
    """NEGATIVE CONTROL (issue #5423 review finding 5).

    The parent already runs on the model a later `spawn_agent` call
    requests, and that spawn fails (`collab spawn failed: ...`, the exact
    text `codex-0.156.0/thread-limit-1.trace.log` records). No span ever
    differs from the parent's own `(model, effort)`, so matching the
    spawn's requested model against completed spans generally (rather than
    against a genuine child span) must not read this as a verified child.
    """
    stderr = (
        codex_stderr(("parent1", "gpt-6-luna", "high", None))
        + codex_spawn_agent_line("gpt-6-luna")
        + "\n"
        + codex_message_line("collab spawn failed: agent thread limit reached")
        + "\n"
        + codex_stderr(("parent2", "gpt-6-luna", "high", "parent1"))
    )

    result = probes.probe_subagent_support(
        _command("codex"), runner=_runner(stdout="", stderr=stderr), timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE


# --- Concurrency ---------------------------------------------------------------


#: `--max-concurrency` was always a placeholder: neither codex nor copilot
#: has ever accepted it (`codex --help` and `copilot --help`, both probed
#: 2026-09-24). It is untrusted now (`TRUSTED_REQUEST_SYNTAX` carries no
#: entry for it), and no currently-trusted harness reaches
#: `probes.probe_concurrency`'s generic JSONL-events branch at all: codex's
#: concurrency_limit is trusted only under `-c agents.max_threads=<n>`,
#: which routes to `_codex_concurrency` and RUST_LOG frames instead, and
#: copilot has no concurrency flag in its real `--help` output at all (the
#: checked-in matrix records copilot's `concurrency_limit` as observed
#: without a request flag, via `_capability_topology` directly on its
#: `subagent.*` events; see `test_harness_capability_live_evidence.py`).
#: The topology arithmetic this branch calls is still pinned directly below
#: (`test_claude_agent_tool_blocks_carry_no_concurrency_boundary`,
#: `test_a_sequential_run_records_a_peak_of_one`, and the three added here),
#: and `test_an_untrusted_concurrency_flag_stays_unverified` is the explicit
#: untrusted-flag control this generic branch now always takes.


def test_an_untrusted_concurrency_flag_stays_unverified() -> None:
    """NEGATIVE CONTROL: `--max-concurrency` was never a real flag on either CLI."""
    result = probes.probe_concurrency(
        _command(requests="3", request_flag="--max-concurrency"),
        requested=3,
        runner=_runner(""),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE
    assert "not trusted" in result.detail


def test_concurrency_peak_below_the_observed_launch_count_is_arithmetic() -> None:
    """CONFIRMATORY: pins `max_concurrent_children`'s walk directly.

    `probes.probe_concurrency`'s own `status`/`value` fields for this same
    input are pinned end to end against the real codex fixture in
    `test_codex_frame_concurrency_below_the_requested_count_stays_unverified`;
    this test isolates the topology arithmetic those fields are built from.
    """
    events = [
        {"type": "subagent.start", "data": {"id": "a"}},
        {"type": "subagent.start", "data": {"id": "b"}},
        {"type": "subagent.complete", "data": {"id": "a"}},
        {"type": "subagent.complete", "data": {"id": "b"}},
        {"type": "subagent.start", "data": {"id": "c"}},
        {"type": "subagent.complete", "data": {"id": "c"}},
    ]

    assert topology.subagent_launch_count(events) == 3
    assert topology.max_concurrent_children(events) == 2


def test_too_few_launches_is_visible_in_the_launch_count() -> None:
    """NEGATIVE CONTROL: a shorter workload cannot prove the requested count."""
    events = [
        {"type": "subagent.start"},
        {"type": "subagent.complete"},
        {"type": "subagent.start"},
        {"type": "subagent.complete"},
    ]

    assert topology.subagent_launch_count(events) == 2


def test_starts_with_no_completion_boundary_cannot_derive_concurrency() -> None:
    """NEGATIVE CONTROL: N starts without ends is N sequential children too."""
    events = [{"type": "subagent.start", "data": {"id": str(index)}} for index in range(4)]

    assert topology.subagent_launch_count(events) == 4
    assert topology.max_concurrent_children(events) is None


def test_codex_frame_concurrency_below_the_requested_count_stays_unverified() -> None:
    """CONFIRMATORY: the real codex fixture, end to end through `probe_concurrency`.

    `codex-0.156.0/concurrency-3-requested.trace.log` requests three
    `gpt-6-luna` children; at most two of their response spans overlap, so
    a requested count of three stays `UNVERIFIED` with `value=2`, matching
    this repository's checked-in matrix.
    """
    stderr = (FIXTURES / "codex-0.156.0" / "concurrency-3-requested.trace.log").read_text(
        encoding="utf-8"
    )
    command = ProbeCommand(
        harness="codex",
        argv=("codex", "exec", "--json", "-m", "gpt-5.6-sol", "-c", "agents.max_threads=3"),
        request_flag="-c",
    )

    result = probes.probe_concurrency(
        command, requested=3, runner=_runner(stdout="", stderr=stderr), timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.BACKEND
    assert result.value == 2


def test_a_parent_on_the_child_model_with_a_failed_spawn_never_verifies_concurrency() -> None:
    """NEGATIVE CONTROL (issue #5423 review finding 5): `peak_overlap` must

    exclude parent spans. The parent already runs on the requested child
    model and its one `spawn_agent` call fails, so there is no genuine
    child span to measure a peak from, even though a naive count of
    "completed spans on the requested model" would find the parent's own.
    """
    stderr = (
        codex_stderr(("parent1", "gpt-6-luna", "high", None))
        + codex_spawn_agent_line("gpt-6-luna")
        + "\n"
        + codex_message_line("collab spawn failed: agent thread limit reached")
        + "\n"
        + codex_stderr(("parent2", "gpt-6-luna", "high", "parent1"))
    )
    command = ProbeCommand(
        harness="codex",
        argv=("codex", "exec", "--json", "-m", "gpt-6-luna", "-c", "agents.max_threads=1"),
        request_flag="-c",
    )

    result = probes.probe_concurrency(
        command, requested=1, runner=_runner(stdout="", stderr=stderr), timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.value is None


def test_a_missing_codex_cli_does_not_crash_the_concurrency_probe() -> None:
    """NEGATIVE CONTROL: same fail-closed path, now on the frame-based codex branch."""
    runner = _runner(raises=FileNotFoundError(2, "No such file or directory", "codex"))
    command = ProbeCommand(
        harness="codex",
        argv=("codex", "exec", "--json", "-m", "gpt-5.6-sol", "-c", "agents.max_threads=2"),
        request_flag="-c",
    )

    result = probes.probe_concurrency(command, requested=2, runner=runner, timeout=TIMEOUT)

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

    assert topology.max_concurrent_children(events) is None


def test_a_sequential_run_records_a_peak_of_one() -> None:
    """CONFIRMATORY: pins the walk, which is arithmetic over the boundaries."""
    events = [
        {"type": "subagent.start"},
        {"type": "subagent.complete"},
        {"type": "subagent.start"},
        {"type": "subagent.complete"},
    ]

    assert topology.max_concurrent_children(events) == 1


def test_concurrency_rejects_a_requested_count_below_one() -> None:
    """NEGATIVE CONTROL: a probe that asks for no children measures nothing."""
    with pytest.raises(ProbeError, match="at least 1"):
        probes.probe_concurrency(_command(), requested=0, runner=_runner(""), timeout=TIMEOUT)
