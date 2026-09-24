"""Codex backend-evidence tests, issue #5423.

Split out of `test_capability_probes.py` and `test_harness_capability_codex_probe.py`
after PR review flagged both files over the 500-line taste-lint limit. Nothing
here is a new test category: it is the codex-specific slice of those two
files, kept together because all three concerns share one root cause. Codex's
`codex exec --json` stdout carries no model or reasoning-effort attribution at
all (probed 2026-09-24, codex-cli 0.156.0); the backend's own answer is only
observable on the client's websocket TRACE log
(`RUST_LOG=tungstenite::protocol=trace`), one `response.completed` frame per
turn on stderr. This file covers:

- The stderr frame parser in `_capability_evidence._codex_response_completed_frames`:
  the real `Received message` shape verifies, and the two forged shapes a
  marker-anywhere search used to accept (a `response.completed` object nested
  inside a `Sending message` request frame, and a non-trace line that merely
  echoes the marker substring) do not.
- The `-c model_reasoning_effort=<value>` request-template rendering codex
  needs for the effort probe, and the GNU short-option `=`-joining edge case
  it does not support.
- `sol_ultra`'s routing through `probe_override`, end to end through the CLI,
  the same as `effort_override`.

No test here runs a real codex CLI. Deterministic cases over an injected fake
runner and recorded runtime output, same convention as the files this split
from.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

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
from tests.eval._harness_capability_test_support import UNPROBED_MATRIX, cli, probes


@pytest.fixture(autouse=True)
def _start_from_the_unprobed_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the CLI default at the pre-probe matrix, not the live-probed one.

    Only the `sol_ultra` CLI-level test below reads `cli.DEFAULT_MATRIX`; the
    rest of this file calls `probes.probe_override` directly and never
    touches it. Harmless as `autouse` either way: `monkeypatch` restores the
    attribute after each test.
    """
    monkeypatch.setattr(cli, "DEFAULT_MATRIX", UNPROBED_MATRIX)


def _which_only(*names: str):
    allowed = set(names)
    return lambda name: f"/bin/{name}" if name in allowed else None


class _CodexEffortRunner:
    """Return a codex version on `--version`, and fixed stdout/stderr otherwise."""

    def __init__(self, *, version: str, stdout: str, stderr: str) -> None:
        self.version = version
        self.stdout = stdout
        self.stderr = stderr
        self.calls: list[list[str]] = []
        self.kwargs: list[dict[str, object]] = []

    def __call__(self, argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        args = [str(value) for value in argv]
        self.calls.append(args)
        self.kwargs.append(dict(_kwargs))
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, self.version, "")
        return subprocess.CompletedProcess(args, 0, self.stdout, self.stderr)


# --- Codex stderr response.completed frame parser -------------------------------


def test_codex_stdout_alone_carries_no_model_and_verifies_nothing() -> None:
    """NEGATIVE CONTROL: codex `--json` stdout names no model or effort at all.

    Probed 2026-09-24, codex-cli 0.156.0: `codex exec --json` stdout emits
    only thread.started, turn.started, item.completed, and turn.completed. A
    model in the stdout event stream (as this fixture plants, mirroring the
    Copilot shape) is not a real codex event and must not be read as backend
    evidence; codex's own evidence lives in stderr, which this run has none of.
    """
    stdout = _jsonl([_answer("hi", model="sol-medium")])

    result = probes.probe_override(
        _plan(harness="codex", parent="sol-low", candidates=("sol-medium",)),
        _command("codex", requests="sol-medium"),
        runner=_runner(stdout),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE
    assert "response.completed" in result.detail


def test_codex_agreeing_response_completed_frames_in_stderr_verify_the_model() -> None:
    """CONFIRMATORY: codex's model evidence comes from stderr, not stdout."""
    stdout = _jsonl([{"type": "turn.completed", "data": {"usage": {}}}])
    frame = (
        '{"type":"response.completed","response":{"model":"sol-medium",'
        '"reasoning":{"effort":"low"}}}'
    )
    stderr = (
        f"2026-09-24T12:00:00Z TRACE tungstenite::protocol: Received message {frame}\n"
        f"2026-09-24T12:00:01Z TRACE tungstenite::protocol: Received message {frame}\n"
    )

    result = probes.probe_override(
        _plan(harness="codex", parent="sol-low", candidates=("sol-medium",)),
        _command("codex", requests="sol-medium"),
        runner=_runner(stdout, stderr=stderr),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.VERIFIED
    assert result.evidence is EvidenceKind.BACKEND


def test_codex_the_real_received_message_shape_verifies_the_model() -> None:
    """POSITIVE: the literal TRACE line codex-cli 0.156.0 emits, probed 2026-09-24.

    `RUST_LOG=tungstenite::protocol=trace` output carries an ISO-8601
    timestamp and a level before the `tungstenite::protocol: Received
    message ` prefix the parser keys on. This is that real shape, verbatim
    apart from the payload, not a hand-trimmed fixture: the parser must
    accept it as-is.
    """
    stdout = _jsonl([{"type": "turn.completed", "data": {"usage": {}}}])
    frame = '{"type":"response.completed","response":{"model":"sol-medium"}}'
    stderr = f"2026-09-24T12:36:36.792998Z TRACE tungstenite::protocol: Received message {frame}\n"

    result = probes.probe_override(
        _plan(harness="codex", parent="sol-low", candidates=("sol-medium",)),
        _command("codex", requests="sol-medium"),
        runner=_runner(stdout, stderr=stderr),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.VERIFIED
    assert result.evidence is EvidenceKind.BACKEND


def test_codex_disagreeing_response_completed_frames_verify_nothing() -> None:
    """NEGATIVE CONTROL: two frames naming different models have no single author."""
    stdout = _jsonl([{"type": "turn.completed", "data": {"usage": {}}}])
    first = '{"type":"response.completed","response":{"model":"sol-medium"}}'
    second = '{"type":"response.completed","response":{"model":"sol-low"}}'
    stderr = (
        f"TRACE tungstenite::protocol: Received message {first}\n"
        f"TRACE tungstenite::protocol: Received message {second}\n"
    )

    result = probes.probe_override(
        _plan(harness="codex", parent="sol-low", candidates=("sol-medium",)),
        _command("codex", requests="sol-medium"),
        runner=_runner(stdout, stderr=stderr),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE
    assert "disagreed" in result.detail


def test_codex_a_request_frame_carrying_a_model_is_not_backend_evidence() -> None:
    """NEGATIVE CONTROL: a client-sent frame is not the backend's own report."""
    stdout = _jsonl([{"type": "turn.completed", "data": {"usage": {}}}])
    stderr = (
        'TRACE tungstenite::protocol: Sending message {"type":"response.create",'
        '"model":"sol-medium"}\n'
    )

    result = probes.probe_override(
        _plan(harness="codex", parent="sol-low", candidates=("sol-medium",)),
        _command("codex", requests="sol-medium"),
        runner=_runner(stdout, stderr=stderr),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE


def test_codex_a_prior_response_completed_nested_in_a_request_frame_is_not_backend_evidence() -> (
    None
):
    """NEGATIVE CONTROL: closes the exact forged shape a marker-anywhere search accepted.

    A `response.create` request frame that embeds a *prior* turn's
    `response.completed` payload (for example because the client echoes
    conversation history back in the request body) reads
    `Sending message {"type":"response.create","prior":{"type":"response.completed",
    "response":{...}}}}` on the wire. The substring `{"type":"response.completed"`
    is present, but not right after `Received message`, because this line
    was sent, not received. Before this fix, `_codex_response_completed_frames`
    searched the whole line for that substring and decoded from wherever it
    first appeared, so this exact shape produced a false BACKEND attribution.
    """
    stdout = _jsonl([{"type": "turn.completed", "data": {"usage": {}}}])
    stderr = (
        'TRACE tungstenite::protocol: Sending message {"type":"response.create",'
        '"prior":{"type":"response.completed","response":{"model":"sol-medium"}}}}\n'
    )

    result = probes.probe_override(
        _plan(harness="codex", parent="sol-low", candidates=("sol-medium",)),
        _command("codex", requests="sol-medium"),
        runner=_runner(stdout, stderr=stderr),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE


def test_codex_a_non_trace_line_echoing_the_marker_is_not_backend_evidence() -> None:
    """NEGATIVE CONTROL: the marker substring alone, outside any TRACE line, proves nothing.

    A line with no `tungstenite::protocol: Received message ` prefix at all
    (for example a stray echo in a different logger, or a test double that
    injects the marker text directly) must not be read as a backend frame
    even when it carries the exact `{"type":"response.completed"` substring.
    """
    stdout = _jsonl([{"type": "turn.completed", "data": {"usage": {}}}])
    stderr = 'codex echo: {"type":"response.completed","response":{"model":"sol-medium"}}\n'

    result = probes.probe_override(
        _plan(harness="codex", parent="sol-low", candidates=("sol-medium",)),
        _command("codex", requests="sol-medium"),
        runner=_runner(stdout, stderr=stderr),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE


def test_codex_a_truncated_response_completed_frame_verifies_nothing() -> None:
    """EDGE: a JSON object cut off mid-stream is skipped, not a crash."""
    stdout = _jsonl([{"type": "turn.completed", "data": {"usage": {}}}])
    stderr = 'TRACE tungstenite::protocol: Received message {"type":"response.completed","respo'

    result = probes.probe_override(
        _plan(harness="codex", parent="sol-low", candidates=("sol-medium",)),
        _command("codex", requests="sol-medium"),
        runner=_runner(stdout, stderr=stderr),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert result.evidence is EvidenceKind.NONE


def test_codex_ultra_requested_against_an_observed_max_stays_unverified() -> None:
    """NEGATIVE CONTROL: probed 2026-09-24, codex-cli 0.156.0: requesting
    `-c model_reasoning_effort=ultra` on `gpt-5.6-sol` produced backend
    `reasoning.effort == "max"`. The classifier must never alias "ultra" onto
    the observed "max"; a differing backend value never verifies.
    """
    stdout = _jsonl([{"type": "turn.completed", "data": {"usage": {}}}])
    frame = '{"type":"response.completed","response":{"reasoning":{"effort":"max"}}}'
    stderr = f"TRACE tungstenite::protocol: Received message {frame}\n"
    command = probes.ProbeCommand(
        harness="codex",
        argv=("codex", "exec", "-m", "gpt-5.6-sol", "-c", "model_reasoning_effort=ultra"),
        request_flag="-c",
    )

    result = probes.probe_override(
        _plan(capability_key="sol_ultra", harness="codex", parent="medium", candidates=("ultra",)),
        command,
        runner=_runner(stdout, stderr=stderr),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.UNVERIFIED
    assert "observed 'max'" in result.detail


def test_the_probe_closes_stdin_so_a_stdin_reading_cli_cannot_hang() -> None:
    """NEGATIVE CONTROL: `codex exec` reads stdin when none is given (probed
    2026-09-24, codex-cli 0.156.0: it prints "Reading additional input from
    stdin..." and blocks), which would hang a probe past its timeout instead
    of exiting.
    """
    seen_kwargs: list[dict[str, object]] = []
    stdout = _jsonl([_answer("hi", model="gpt-5.6-sol")])

    probes.probe_override(
        _plan(), _command(), runner=_runner(stdout, seen_kwargs=seen_kwargs), timeout=TIMEOUT
    )

    assert seen_kwargs[0]["stdin"] is subprocess.DEVNULL


# --- Request template rendering -------------------------------------------------


def test_codex_effort_verifies_through_the_dash_c_template() -> None:
    """CONFIRMATORY: `-c model_reasoning_effort=<value>` is codex's trusted request."""
    stdout = _jsonl([{"type": "turn.completed", "data": {"usage": {}}}])
    frame = '{"type":"response.completed","response":{"reasoning":{"effort":"low"}}}'
    stderr = f"TRACE tungstenite::protocol: Received message {frame}\n"
    command = probes.ProbeCommand(
        harness="codex",
        argv=("codex", "exec", "-m", "gpt-5.6-sol", "-c", "model_reasoning_effort=low"),
        request_flag="-c",
    )

    result = probes.probe_override(
        _plan(
            capability_key="effort_override", harness="codex", parent="medium", candidates=("low",)
        ),
        command,
        runner=_runner(stdout, stderr=stderr),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.VERIFIED
    assert result.evidence is EvidenceKind.BACKEND


def test_codex_a_bare_unformatted_value_after_dash_c_does_not_carry_the_request() -> None:
    """NEGATIVE CONTROL: `-c low` is not the rendered request `-c model_reasoning_effort=low`.

    A command carrying only the unformatted value after `-c` must be refused
    before any CLI runs, the same as a command that omits the request
    entirely: reading it as bound would make an unrendered argv look like the
    real codex request syntax.
    """
    seen: list[list[str]] = []
    command = probes.ProbeCommand(
        harness="codex",
        argv=("codex", "exec", "-m", "gpt-5.6-sol", "-c", "low"),
        request_flag="-c",
    )

    with pytest.raises(ProbeError, match="does not request"):
        probes.probe_override(
            _plan(
                capability_key="effort_override",
                harness="codex",
                parent="medium",
                candidates=("low",),
            ),
            command,
            runner=_runner("", seen=seen),
            timeout=TIMEOUT,
        )

    assert seen == []


def test_codex_a_dash_c_equals_joined_token_does_not_carry_the_request() -> None:
    """NEGATIVE CONTROL: a short GNU option does not support `flag=value` syntax.

    `codex exec --help` (codex-cli 0.156.0, read 2026-09-24) documents `-c` as
    `-c, --config <key=value>`, not `-c=<key=value>`; only the long spelling
    `--config=model_reasoning_effort=low` would use `=` at all, and this
    module's templates always render `-c`, never `--config`.
    """
    command = probes.ProbeCommand(
        harness="codex",
        argv=("codex", "exec", "-m", "gpt-5.6-sol", "-c=model_reasoning_effort=low"),
        request_flag="-c",
    )

    with pytest.raises(ProbeError, match="does not request"):
        probes.probe_override(
            _plan(
                capability_key="effort_override",
                harness="codex",
                parent="medium",
                candidates=("low",),
            ),
            command,
            runner=_runner(""),
            timeout=TIMEOUT,
        )


def test_copilot_effort_equals_joined_flag_still_carries_the_request() -> None:
    """CONFIRMATORY: a long option keeps the `flag=value` acceptance."""
    stdout = _jsonl([_answer("hi", reasoningEffort="low")])
    command = probes.ProbeCommand(
        harness="copilot",
        argv=("copilot", "--reasoning-effort=low"),
        request_flag="--reasoning-effort",
    )

    result = probes.probe_override(
        _plan(capability_key="effort_override", parent="medium", candidates=("low",)),
        command,
        runner=_runner(stdout),
        timeout=TIMEOUT,
    )

    assert result.status is CapabilityStatus.VERIFIED


# --- sol_ultra routes through probe_override, like effort_override -------------


def test_sol_ultra_behavioral_probe_routes_through_probe_override(
    tmp_path: Path, monkeypatch
) -> None:
    """POSITIVE: `_run_behavioral_probe` treats sol_ultra as an override capability."""
    output = tmp_path / "report.json"
    plan = tmp_path / "probes.json"
    plan.write_text(
        json.dumps(
            {
                "probes": [
                    {
                        "harness": "codex",
                        "capability": "sol_ultra",
                        "parent_value": "medium",
                        "child_value": "ultra",
                        "argv": ["codex", "exec", "--json", "-m", "gpt-5.6-sol"],
                        "request_flag": "-c",
                        "env": {"RUST_LOG": "tungstenite::protocol=trace"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli.shutil, "which", _which_only("codex"))
    frame = '{"type":"response.completed","response":{"reasoning":{"effort":"ultra"}}}'
    runner = _CodexEffortRunner(
        version="codex-cli 0.156.0",
        stdout=json.dumps({"type": "turn.completed", "data": {"usage": {}}}) + "\n",
        stderr=f"TRACE tungstenite::protocol: Received message {frame}\n",
    )

    code = cli.main(
        ["--output", str(output), "--behavioral-probes", str(plan)],
        runner=runner,
    )

    assert code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    codex = next(row for row in report["harnesses"] if row["harness"] == "codex")
    assert codex["capabilities"]["sol_ultra"]["status"] == "VERIFIED"
    # sol_ultra is not effort_override: it must not silently widen supported_efforts.
    assert codex["supported_efforts"] == []
