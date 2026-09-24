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
            "-m",
            "gpt-5.6-sol",
            request_flag,
            rendered_value,
        ),
        request_flag=request_flag,
    )


# --- codex: model_override, effort_override, subagent_support --------------------


def test_codex_model_override_verifies_from_the_raw_subagent_luna_high_fixture() -> None:
    stderr = _codex_stderr("subagent-luna-high.trace.log")
    command = _codex_command(request_flag="--model", request_value="gpt-6-luna")

    result = probes.probe_override(
        _plan(harness="codex", parent="gpt-5.6-sol", candidates=("gpt-6-luna",)),
        command,
        runner=_runner(stdout="", stderr=stderr),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.VERIFIED
    assert result.evidence is EvidenceKind.BACKEND


def test_codex_effort_override_verifies_from_the_raw_subagent_luna_high_fixture() -> None:
    stderr = _codex_stderr("subagent-luna-high.trace.log")
    command = _codex_command(request_flag="-c", request_value="high")

    result = probes.probe_override(
        _plan(
            harness="codex",
            capability_key="effort_override",
            parent="medium",
            candidates=("high",),
        ),
        command,
        runner=_runner(stdout="", stderr=stderr),
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


def test_copilot_model_override_verifies_from_the_raw_wire_and_events_fixtures(tmp_path) -> None:
    wire_text = (COPILOT_FIXTURES / "child-model-override.wire.log").read_text()
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
            "--model",
            "claude-sonnet-4-6",
        ),
        request_flag="--model",
    )
    stdout = _copilot_events("child-model-override.events.jsonl")

    result = probes.probe_override(
        _plan(parent="claude-haiku-4-5-20251001", candidates=("claude-sonnet-4-6",)),
        command,
        runner=_runner(stdout),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.VERIFIED
    assert result.evidence is EvidenceKind.BACKEND


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


def test_copilot_subagent_support_verifies_from_the_raw_events_fixture() -> None:
    stdout = _copilot_events("child-model-override.events.jsonl")
    command = ProbeCommand(harness="copilot", argv=("copilot", "-p", "probe"))

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
