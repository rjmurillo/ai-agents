"""Shared fixtures for the capability-probe tests (issue #5423 step 2).

Recorded runtime output shapes and an injected fake runner. Nothing here
reaches the network, PATH, or a real CLI. The runner dispatches on argv rather
than call order, so a probe that stops issuing a command fails loudly instead
of silently consuming the next entry in a positional list.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tests.eval._harness_capability_test_support import capability, probes

CapabilityStatus = capability.CapabilityStatus
EvidenceKind = capability.EvidenceKind
HarnessCapabilityError = capability.HarnessCapabilityError
ProbeError = probes.ProbeError
ProbeCommand = probes.ProbeCommand

TIMEOUT = 5.0

#: The literal text codex writes between a RUST_LOG timestamp/level prefix
#: and the JSON payload, quoted from
#: `codex-0.156.0/subagent-luna-high.trace.log`.
CODEX_FRAME_MARKER = " TRACE tungstenite::protocol: Received message "

#: The literal text every Copilot `--log-level all` debug line carries,
#: quoted from `copilot-1.0.89-byok-anthropic/child-model-override.wire.log`.
COPILOT_WIRE_MARKER = "[rust:model_wire] "


def _codex_frame_line(
    kind: str,
    response_id: str,
    model: str,
    effort: str,
    *,
    previous: str | None = None,
    ts: str = "2026-09-24T12:00:00.000000Z",
) -> str:
    """Build one RUST_LOG trace line for `_codex_frames.parse_codex_frames`."""
    prev = "null" if previous is None else f'"{previous}"'
    return (
        f"{ts}{CODEX_FRAME_MARKER}"
        f'{{"type": "{kind}", "response": {{"id": "{response_id}", "model": "{model}", '
        f'"previous_response_id": {prev}, "reasoning": {{"effort": "{effort}"}}}}}}'
    )


def codex_spawn_agent_line(model: str | None, *, ts: str = "2026-09-24T12:00:00.500000Z") -> str:
    """Build a `response.output_item.done` `spawn_agent` function-call frame."""
    args = {"fork_turns": "none", "task_name": "task_1"}
    if model is not None:
        args["model"] = model
    arguments = json.dumps(args).replace('"', '\\"')
    return (
        f"{ts}{CODEX_FRAME_MARKER}"
        '{"type": "response.output_item.done", "item": {"type": "function_call", '
        f'"name": "spawn_agent", "arguments": "{arguments}"}}}}'
    )


def codex_message_line(text: str, *, ts: str = "2026-09-24T12:00:01.000000Z") -> str:
    """Build a `response.output_item.done` message frame carrying `text`."""
    escaped = text.replace('"', '\\"')
    return (
        f"{ts}{CODEX_FRAME_MARKER}"
        '{"type": "response.output_item.done", "item": {"type": "message", '
        f'"content": [{{"type": "output_text", "text": "{escaped}"}}]}}}}'
    )


def codex_stderr(*spans: tuple[str, str, str, str | None]) -> str:
    """Build stderr text for a sequence of `(id, model, effort, previous)` spans.

    Each span is emitted as a `response.created` immediately followed by its
    `response.completed`, which is enough for `observe_codex_model`/
    `observe_codex_effort` (they read `response.created`) without needing
    the finer-grained open/close interleaving `peak_overlap` tests exercise
    directly in `tests/eval/test_codex_frames.py`.
    """
    lines: list[str] = []
    for response_id, model, effort, previous in spans:
        for kind in ("response.created", "response.completed"):
            lines.append(_codex_frame_line(kind, response_id, model, effort, previous=previous))
    return "\n".join(lines) + "\n"


def copilot_wire_log_dir(tmp_path: Path, text: str) -> Path:
    """Write `text` as a `process-*.log` file and return its containing directory.

    Mirrors the shape `_capability_probes._capture_copilot_wire` reads: a
    `--log-dir <dir>` whose directory holds one or more `process-*.log`
    files.
    """
    log_dir = tmp_path / "copilot-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "process-1.log").write_text(text, encoding="utf-8")
    return log_dir


def copilot_wire_response_line(
    request_id: str, response_id: str, model: str, *, ts: str = "2026-09-24T12:53:39.142Z"
) -> str:
    """Build the three-line `response (Request-ID ...)/data:/{json}` block."""
    return (
        f"{ts} [DEBUG] {COPILOT_WIRE_MARKER}response (Request-ID {request_id}):\n"
        f"{ts} [DEBUG] {COPILOT_WIRE_MARKER}data:\n"
        f'{ts} [DEBUG] {COPILOT_WIRE_MARKER}{{"id": "{response_id}", "model": "{model}", '
        f'"usage": {{"prompt_tokens": 1}}}}\n'
    )


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


def _command(
    harness: str = "copilot",
    *,
    requests: str | None = "gpt-5.6-sol",
    request_flag: str = "--model",
    env: Mapping[str, str] | None = None,
) -> probes.ProbeCommand:
    """Build a command that actually asks for `requests`.

    `probe_override` refuses a command that does not carry its plan's child
    value, so the requested value is part of the argv rather than implied.
    Pass `requests=None` to build the unbound command that refusal is about.
    """
    argv = [harness, "--prompt", "probe"]
    if requests is not None:
        argv += [request_flag, requests]
    return ProbeCommand(
        harness=harness,
        argv=tuple(argv),
        env=env,
        request_flag=request_flag,
    )


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
