"""Tests for capability probe execution, issue #5423 step 2.

Deterministic cases over an injected fake runner and recorded runtime
output. No network, no PATH lookup, no real CLI. No test writes to
`scripts/eval/examples/harness-capability-matrix.json`; the honesty of that
file is pinned by `test_harness_capability.py`. Plan construction is
covered by `test_capability_probe_plans.py`.

Discrimination. Twenty-one mutations were run against `_capability_probes.py`,
each removing or weakening one guard, with `__pycache__` cleared between every
mutation and its rerun. All twenty-one were killed, a behavior-preserving
inverted control survived, and the restored file was byte-compared against the
original. Every case marked NEGATIVE CONTROL below failed under at least one of
those mutations and is named by it. Cases marked CONFIRMATORY survived all
twenty-one, or failed only as collateral of a mutation aimed at a different
case; they are labeled because they are not evidence that any guard works.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from tests.eval._capability_probe_fixtures import (
    TIMEOUT,
    CapabilityStatus,
    EvidenceKind,
    HarnessCapabilityError,
    ProbeCommand,
    ProbeError,
    _answer,
    _command,
    _jsonl,
    _plan,
    _runner,
    _session_change,
    codex_stderr,
    copilot_wire_log_dir,
    copilot_wire_response_line,
)
from tests.eval._harness_capability_test_support import evidence, probes

# --- Model override probe ------------------------------------------------------


def test_a_codex_child_that_answers_on_the_requested_model_verifies_the_override() -> None:
    """CONFIRMATORY: codex reads backend evidence from RUST_LOG stderr frames.

    Neither harness's model_override reaches VERIFIED from `--json` stdout
    any more: codex never carried backend evidence there at all, and
    Copilot's `assistant.message.model` was found to be a client label (see
    `test_a_copilot_child_wire_response_verifies_the_override` below and
    `_capability_evidence.observe_copilot_model`).
    """
    stderr = codex_stderr(
        ("parent", "gpt-5.6-sol", "medium", None),
        ("child", "gpt-6-luna", "high", None),
    )

    result = probes.probe_override(
        _plan(harness="codex", parent="gpt-5.6-sol", candidates=("gpt-6-luna",)),
        _command("codex", requests="gpt-6-luna"),
        runner=_runner(stdout="", stderr=stderr),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.VERIFIED
    assert result.evidence is EvidenceKind.BACKEND


def test_a_copilot_child_wire_response_verifies_the_override(tmp_path) -> None:
    """CONFIRMATORY: copilot reads backend evidence from its `--log-dir` wire log."""
    wire_text = copilot_wire_response_line("req_1", "msg_1", "claude-sonnet-4-6")
    log_dir = copilot_wire_log_dir(tmp_path, wire_text)
    command = ProbeCommand(
        harness="copilot",
        argv=(
            "copilot",
            "--prompt",
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
    stdout = _jsonl(
        [{"type": "assistant.message", "data": {"content": "hi", "apiCallId": "msg_1"}}]
    )

    result = probes.probe_override(
        _plan(parent="claude-haiku-4-5-20251001", candidates=("claude-sonnet-4-6",)),
        command,
        runner=_runner(stdout),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.VERIFIED
    assert result.evidence is EvidenceKind.BACKEND


def test_only_the_newest_log_dir_file_is_read(tmp_path) -> None:
    """NEGATIVE CONTROL (issue #5423 review finding 8): a stale `process-*.log`

    left behind by an earlier run in a reused `--log-dir` must not have its
    wire evidence joined into this run's. An older file here names a
    response for a `msg_1` the current run's stdout never mentions, and a
    younger file (created after, so its mtime sorts last) is the one that
    actually answers this run's `apiCallId`.
    """
    log_dir = tmp_path / "copilot-logs"
    log_dir.mkdir()
    stale = log_dir / "process-1.log"
    stale.write_text(
        copilot_wire_response_line("req_stale", "msg_stale", "claude-opus-4"), encoding="utf-8"
    )
    newest = log_dir / "process-2.log"
    newest.write_text(
        copilot_wire_response_line("req_1", "msg_1", "claude-sonnet-4-6"), encoding="utf-8"
    )
    now = os.stat(newest).st_mtime
    os.utime(stale, (now - 60, now - 60))
    command = ProbeCommand(
        harness="copilot",
        argv=(
            "copilot",
            "--prompt",
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
    stdout = _jsonl(
        [{"type": "assistant.message", "data": {"content": "hi", "apiCallId": "msg_1"}}]
    )

    result = probes.probe_override(
        _plan(parent="claude-haiku-4-5-20251001", candidates=("claude-sonnet-4-6",)),
        command,
        runner=_runner(stdout),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.VERIFIED
    assert "msg_stale" not in result.detail


def test_an_echo_only_output_with_no_log_dir_never_verifies_the_override(tmp_path) -> None:
    """NEGATIVE CONTROL: missing wire evidence is UNVERIFIED, never CLIENT_ECHO-as-proof.

    `_capture_copilot_wire` requires the caller to have already asked for
    `--log-level all --log-dir <dir>`; a plan that omits it gets a detail
    naming that flag instead of silently trusting `assistant.message.model`.
    """
    stdout = _jsonl([_session_change(newModel="gpt-5.6-sol"), _answer("hi")])
    command = ProbeCommand(
        harness="copilot",
        argv=("copilot", "--prompt", "probe", "--model", "gpt-5.6-sol"),
        request_flag="--model",
    )

    result = probes.probe_override(
        _plan(parent="claude-opus-5", candidates=("gpt-5.6-sol",)),
        command,
        runner=_runner(stdout),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE
    assert "--log-dir" in result.detail


def test_a_codex_child_that_silently_inherits_the_parent_never_verifies() -> None:
    """NEGATIVE CONTROL: a child span reporting the parent's own model is not an override.

    Every span's model equals `parent_value`, so `_codex_candidate_spans`
    excludes all of them: there is no span left that could be a child's own
    answer, which is exactly what a codex run that silently ignored
    `spawn_agent`'s `model` argument would look like on the wire.
    """
    stderr = codex_stderr(
        ("parent", "gpt-5.6-sol", "medium", None),
        ("child", "gpt-5.6-sol", "medium", None),
    )

    result = probes.probe_override(
        _plan(harness="codex", parent="gpt-5.6-sol", candidates=("gpt-6-luna",)),
        _command("codex", requests="gpt-6-luna"),
        runner=_runner(stdout="", stderr=stderr),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert "parent" in result.detail


def test_a_hand_built_plan_with_an_equal_child_value_cannot_be_constructed() -> None:
    """NEGATIVE CONTROL: the discrimination guard binds the dataclass, not only the builder.

    `OverridePlan` is public, so a caller can skip `build_override_plan`. An
    equal-value plan whose backend echoes that value would otherwise reach
    `classify_override`, which is the last line of defense rather than the
    first.
    """
    with pytest.raises(ProbeError, match="does not differ from parent"):
        probes.OverridePlan(
            capability="model_override",
            harness="copilot",
            parent_value="gpt-5.6-sol",
            child_value="gpt-5.6-sol",
        )


def test_a_hand_built_plan_differing_only_by_case_cannot_be_constructed() -> None:
    """NEGATIVE CONTROL: `classify_override` compares with ==, so case slipped past it."""
    with pytest.raises(ProbeError, match="does not differ from parent"):
        probes.OverridePlan(
            capability="effort_override",
            harness="copilot",
            parent_value="Sol Ultra",
            child_value="sol ultra",
        )


def test_a_hand_built_plan_differing_only_by_whitespace_cannot_be_constructed() -> None:
    """NEGATIVE CONTROL: the other form == accepts as a difference."""
    with pytest.raises(ProbeError, match="does not differ from parent"):
        probes.OverridePlan(
            capability="effort_override",
            harness="copilot",
            parent_value="Sol Ultra",
            child_value="  Sol Ultra  ",
        )


def test_two_answer_turns_naming_different_models_verify_nothing() -> None:
    """NEGATIVE CONTROL: a blended answer has no single author."""
    stdout = _jsonl(
        [_answer("first", model="gpt-5.6-sol"), _answer("second", model="claude-opus-5")]
    )

    result = probes.probe_override(_plan(), _command(), runner=_runner(stdout), timeout=TIMEOUT)

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE


def test_codex_exiting_zero_with_no_stderr_frames_fails_closed() -> None:
    """NEGATIVE CONTROL: codex has an in-tree frame parser now, but it needs
    `RUST_LOG=tungstenite::protocol=trace` to have anything to read. A codex
    run that exits 0 with empty stderr means the caller forgot that
    environment variable, a misconfigured plan rather than a negative
    capability result, so this raises instead of resolving to `UNVERIFIED`
    (compare `test_malformed_runtime_output_fails_closed_rather_than_degrading`,
    the equivalent control for `--json` stdout).
    """
    stdout = _jsonl([_answer("hi", model="sol-medium")])

    with pytest.raises(ProbeError, match="RUST_LOG=tungstenite::protocol=trace"):
        probes.probe_override(
            _plan(harness="codex", parent="sol-low", candidates=("sol-medium",)),
            _command("codex", requests="sol-medium"),
            runner=_runner(stdout),
            timeout=TIMEOUT,
        )


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
        _command("claude", requests="claude-opus-5"),
        runner=_runner(stdout),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE


def test_the_probe_passes_the_command_argv_through_verbatim() -> None:
    """CONFIRMATORY: pins the injected-runner seam."""
    seen: list[list[str]] = []
    stdout = _jsonl([_answer("hi", model="gpt-5.6-sol")])

    probes.probe_override(_plan(), _command(), runner=_runner(stdout, seen=seen), timeout=TIMEOUT)

    assert seen == [["copilot", "--prompt", "probe", "--model", "gpt-5.6-sol"]]


# --- Effort override probe -----------------------------------------------------


#: These five tests exercise `_capability_evidence.observe_effort` directly
#: rather than through `probes.probe_override`. That pipeline no longer
#: reaches this function for either currently-trusted harness: codex reads
#: `observe_codex_effort` from RUST_LOG frames and copilot reads
#: `observe_copilot_effort` from its wire log (both added when copilot's
#: `assistant.message.model` was found to be a client label, see
#: `test_capability_evidence.py`). `observe_effort` itself is unchanged and
#: still the generic events-path a future harness could use, so its own
#: key-matching behavior is still worth pinning in isolation.


def test_an_effort_on_an_answer_turn_verifies_the_override() -> None:
    """CONFIRMATORY: happy path for the effort observable."""
    events = [_answer("hi", reasoningEffort="Sol Ultra")]

    observation = evidence.observe_effort("copilot", events)

    assert observation.evidence is EvidenceKind.BACKEND
    assert observation.observed == "Sol Ultra"


def test_an_effort_read_from_session_state_never_verifies() -> None:
    """NEGATIVE CONTROL: session state is the request echoed back."""
    events = [_session_change(reasoningEffort="Sol Ultra"), _answer("hi")]

    observation = evidence.observe_effort("copilot", events)

    assert observation.evidence is EvidenceKind.CLIENT_ECHO
    assert observation.observed == "Sol Ultra"


def test_an_effort_on_a_contentless_turn_is_not_backend_evidence() -> None:
    """NEGATIVE CONTROL: a status line is not an answer the backend produced."""
    events = [{"type": "assistant.message", "data": {"reasoningEffort": "Sol Ultra"}}]

    observation = evidence.observe_effort("copilot", events)

    assert observation.evidence is EvidenceKind.NONE


def test_an_effort_key_outside_the_configured_set_observes_nothing() -> None:
    """NEGATIVE CONTROL: the key set is a bounded allowlist, not a scan."""
    events = [_answer("hi", tier="Sol Ultra")]

    observation = evidence.observe_effort("copilot", events)

    assert observation.evidence is EvidenceKind.NONE


def test_a_caller_supplied_effort_key_is_honored() -> None:
    """CONFIRMATORY: a live run can name the real key without a code change."""
    events = [_answer("hi", tier="Sol Ultra")]

    observation = evidence.observe_effort("copilot", events, effort_keys=("tier",))

    assert observation.evidence is EvidenceKind.BACKEND
    assert observation.observed == "Sol Ultra"


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
