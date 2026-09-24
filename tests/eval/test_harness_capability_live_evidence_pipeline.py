"""Runner-backed pipeline re-derivation (issue #5423 review finding 7).

`test_harness_capability_live_evidence.py` and
`test_harness_capability_live_evidence_copilot.py` re-derive each
`VERIFIED` cell by calling the observation functions
(`_capability_evidence.observe_codex_model`, `_capability_topology.*`, ...)
directly on parsed fixture data. This file instead feeds the raw,
unmodified fixture *text* through the actual entry points a live run
uses -- `probes.probe_override`, `probes.probe_subagent_support`,
`probes.probe_concurrency` -- with a fake runner standing in for the
subprocess call, so the trust gates, capture, and classification the real
pipeline runs are all exercised together, not just the observation layer.
"""

from __future__ import annotations

import pytest

from tests.eval._capability_probe_fixtures import (
    TIMEOUT,
    CapabilityStatus,
    EvidenceKind,
    ProbeCommand,
    _plan,
    _runner,
    copilot_wire_log_dir,
)
from tests.eval._harness_capability_test_support import FIXTURES, probes

CODEX_FIXTURES = FIXTURES / "codex-0.156.0"
COPILOT_FIXTURES = FIXTURES / "copilot-1.0.89-byok-anthropic"


def _codex_stderr(name: str) -> str:
    return (CODEX_FIXTURES / name).read_text(encoding="utf-8")


def _copilot_events(name: str) -> str:
    return (COPILOT_FIXTURES / name).read_text(encoding="utf-8")


def _codex_command(*, request_flag: str, request_value: str) -> ProbeCommand:
    rendered_value = (
        request_value if request_flag == "--model" else f"model_reasoning_effort={request_value}"
    )
    return ProbeCommand(
        harness="codex",
        argv=(
            "codex",
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--ephemeral",
            "-s",
            "read-only",
            request_flag,
            rendered_value,
        ),
        request_flag=request_flag,
    )


# --- codex: model_override, effort_override, subagent_support --------------------


_CODEX_STDOUT = '{"type": "thread.started", "thread_id": "t1"}\n'


def test_codex_model_override_verifies_from_the_raw_terra_high_fixture() -> None:
    stderr = _codex_stderr("terra-high.trace.log")
    command = _codex_command(request_flag="--model", request_value="gpt-5.6-terra")

    result = probes.probe_override(
        _plan(harness="codex", parent="gpt-6-sol", candidates=("gpt-5.6-terra",)),
        command,
        runner=_runner(stdout=_CODEX_STDOUT, stderr=stderr),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.VERIFIED
    assert result.evidence is EvidenceKind.BACKEND


def test_codex_parent_and_child_frames_do_not_verify_a_top_level_override() -> None:
    """NEGATIVE CONTROL: a subagent run's frames disagree, so no single value wins.

    `probe_override` reads one agreeing `response.completed` value. Parent and
    child verification lives in `observe_codex_model`, not this path.
    """
    stderr = _codex_stderr("subagent-luna-high.trace.log")
    command = _codex_command(request_flag="--model", request_value="gpt-6-luna")

    result = probes.probe_override(
        _plan(harness="codex", parent="gpt-5.6-sol", candidates=("gpt-6-luna",)),
        command,
        runner=_runner(stdout=_CODEX_STDOUT, stderr=stderr),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED


def test_codex_effort_override_verifies_from_the_raw_sol_6_low_fixture() -> None:
    stderr = _codex_stderr("sol-6-low.trace.log")
    command = _codex_command(request_flag="-c", request_value="low")

    result = probes.probe_override(
        _plan(
            harness="codex",
            capability_key="effort_override",
            parent="medium",
            candidates=("low",),
        ),
        command,
        runner=_runner(stdout=_CODEX_STDOUT, stderr=stderr),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.VERIFIED
    assert result.evidence is EvidenceKind.BACKEND


def test_codex_subagent_support_verifies_from_the_raw_subagent_luna_high_fixture() -> None:
    stderr = _codex_stderr("subagent-luna-high.trace.log")
    command = ProbeCommand(harness="codex", argv=("codex", "exec", "--json", "-m", "gpt-5.6-sol"))

    result = probes.probe_subagent_support(
        command, runner=_runner(stdout="", stderr=stderr), timeout=TIMEOUT
    )

    assert result.status is CapabilityStatus.VERIFIED
    assert result.evidence is EvidenceKind.BACKEND


def test_codex_concurrency_stays_unverified_from_the_raw_concurrency_fixture() -> None:
    stderr = _codex_stderr("concurrency-3-requested.trace.log")
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


# --- copilot: model_override, effort_override, subagent_support ------------------


def _copilot_model_command(log_dir, model: str) -> ProbeCommand:
    return ProbeCommand(
        harness="copilot",
        argv=(
            "copilot",
            "-p",
            "probe",
            "--log-level",
            "all",
            "--log-dir",
            str(log_dir),
            "--model",
            model,
        ),
        request_flag="--model",
    )


def test_copilot_top_level_alias_request_does_not_verify_against_the_dated_id(tmp_path) -> None:
    """NEGATIVE CONTROL: the parent asked for `claude-haiku-4-5` and the provider
    answered `claude-haiku-4-5-20251001`; the alias is never folded onto it."""
    wire_text = (COPILOT_FIXTURES / "child-model-override.wire.log").read_text()
    command = _copilot_model_command(copilot_wire_log_dir(tmp_path, wire_text), "claude-haiku-4-5")

    result = probes.probe_override(
        _plan(parent="claude-sonnet-4-6", candidates=("claude-haiku-4-5",)),
        command,
        runner=_runner(_copilot_events("child-model-override.events.jsonl")),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED


def test_copilot_child_on_the_requested_model_does_not_verify_a_top_level_override(
    tmp_path,
) -> None:
    """NEGATIVE CONTROL: only the child ran `claude-sonnet-4-6`; the parent did not."""
    wire_text = (COPILOT_FIXTURES / "child-model-override.wire.log").read_text()
    command = _copilot_model_command(copilot_wire_log_dir(tmp_path, wire_text), "claude-sonnet-4-6")

    result = probes.probe_override(
        _plan(parent="claude-haiku-4-5-20251001", candidates=("claude-sonnet-4-6",)),
        command,
        runner=_runner(_copilot_events("child-model-override.events.jsonl")),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED


def test_copilot_effort_override_stays_client_echo_from_the_raw_wire_fixture(tmp_path) -> None:
    wire_text = (COPILOT_FIXTURES / "effort-high.wire.log").read_text()
    log_dir = copilot_wire_log_dir(tmp_path, wire_text)
    command = ProbeCommand(
        harness="copilot",
        argv=(
            "copilot",
            "-p",
            "probe",
            "--log-level",
            "all",
            "--log-dir",
            str(log_dir),
            "--reasoning-effort",
            "high",
        ),
        request_flag="--reasoning-effort",
    )
    stdout = _copilot_events("child-model-override.events.jsonl")

    result = probes.probe_override(
        _plan(capability_key="effort_override", parent="low", candidates=("high",)),
        command,
        runner=_runner(stdout),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.CLIENT_ECHO


def test_copilot_subagent_support_verifies_from_the_raw_events_fixture(tmp_path) -> None:
    stdout = _copilot_events("child-model-override.events.jsonl")
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    wire = (COPILOT_FIXTURES / "child-model-override.wire.log").read_text(encoding="utf-8")
    (log_dir / "process-1.log").write_text(wire, encoding="utf-8")
    command = ProbeCommand(
        harness="copilot", argv=("copilot", "-p", "probe", "--log-dir", str(log_dir))
    )

    result = probes.probe_subagent_support(command, runner=_runner(stdout), timeout=TIMEOUT)

    assert result.status is CapabilityStatus.VERIFIED
    assert result.evidence is EvidenceKind.BACKEND


def test_copilot_concurrency_is_refused_before_any_capture(tmp_path) -> None:
    """Copilot has no trusted `concurrency_limit` request flag at all, so the

    real `concurrency-3-requested.events.jsonl` fixture is never even read;
    the trust gate in `probe_concurrency` refuses the plan first.
    """
    command = ProbeCommand(
        harness="copilot",
        argv=("copilot", "-p", "probe", "--max-concurrency", "3"),
        request_flag="--max-concurrency",
    )
    stdout = _copilot_events("concurrency-3-requested.events.jsonl")

    result = probes.probe_concurrency(command, requested=3, runner=_runner(stdout), timeout=TIMEOUT)

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE
    assert "not trusted" in result.detail


def test_copilot_relative_log_dir_resolves_against_the_probe_cwd(tmp_path) -> None:
    wire_text = (COPILOT_FIXTURES / "child-model-override.wire.log").read_text()
    copilot_wire_log_dir(tmp_path, wire_text)
    log_dir_name = "copilot-logs"
    command = ProbeCommand(
        harness="copilot",
        argv=("copilot", "-p", "probe", "--log-dir", log_dir_name),
        cwd=tmp_path,
    )

    result = probes.probe_subagent_support(
        command,
        runner=_runner(_copilot_events("child-model-override.events.jsonl")),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.VERIFIED


def test_copilot_a_stale_wire_log_never_verifies_subagent_support(tmp_path) -> None:
    """NEGATIVE CONTROL: responses from another run share no apiCallId."""
    wire_text = (COPILOT_FIXTURES / "concurrency-3-requested.wire.log").read_text()
    log_dir = copilot_wire_log_dir(tmp_path, wire_text)
    command = ProbeCommand(
        harness="copilot", argv=("copilot", "-p", "probe", "--log-dir", str(log_dir))
    )

    result = probes.probe_subagent_support(
        command,
        runner=_runner(_copilot_events("child-model-override.events.jsonl")),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.CLIENT_ECHO


def test_copilot_an_unreadable_wire_log_raises_probe_error(tmp_path) -> None:
    log_dir = tmp_path / "logs"
    (log_dir / "process-1.log").mkdir(parents=True)
    command = ProbeCommand(
        harness="copilot", argv=("copilot", "-p", "probe", "--log-dir", str(log_dir))
    )

    with pytest.raises(probes.ProbeError, match="could not be read"):
        probes.probe_subagent_support(
            command,
            runner=_runner(_copilot_events("child-model-override.events.jsonl")),
            timeout=TIMEOUT,
        )
