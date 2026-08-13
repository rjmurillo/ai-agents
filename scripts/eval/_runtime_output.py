"""Parse machine-readable output from runtime parity subprocesses."""

from __future__ import annotations

import json


class RuntimeOutputError(RuntimeError):
    """A CLI emitted malformed machine-readable output."""


def runtime_failure_record(
    harness: str,
    command: list[str],
    *,
    exit_code: int | None,
    error: str,
    raw_output: str = "",
) -> dict[str, object]:
    """Build the stable report shape for a failed runtime invocation."""
    return {
        "provenance": (
            "Claude runtime" if harness == "claude" else "Copilot runtime"
        ),
        "command": command,
        "exit_code": exit_code,
        "resolved_model": None,
        "raw_output": raw_output,
        "response": "",
        "question_mechanism": None,
        "tool_events": [],
        "subagent_events": [],
        "assertions": [],
        "error": error,
        "passed": False,
    }


def parse_events(stdout: str) -> list[dict[str, object]]:
    """Parse JSONL events and reject every malformed nonblank line."""
    events: list[dict[str, object]] = []
    for line_number, line in enumerate(stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeOutputError(
                f"runtime output line {line_number} is not valid JSON"
            ) from exc
        if not isinstance(event, dict):
            raise RuntimeOutputError(
                f"runtime output line {line_number} must be a JSON object"
            )
        events.append(event)
    return events
