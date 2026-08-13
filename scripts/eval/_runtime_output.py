"""Parse machine-readable output from runtime parity subprocesses."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence


class RuntimeOutputError(RuntimeError):
    """A CLI emitted malformed machine-readable output."""


QUESTION_TOOLS = frozenset({"askuserquestion", "ask_user", "askuser", "ask-user"})


def _tool_name(event: object) -> str:
    if not isinstance(event, Mapping):
        return ""
    data = event.get("data")
    if isinstance(data, Mapping):
        for key in ("toolName", "name", "tool"):
            value = data.get(key)
            if isinstance(value, str):
                return value
    name = event.get("name")
    return name if isinstance(name, str) else ""


def question_mechanism(tools: Sequence[object], response: str) -> str:
    """Name the branch the harness actually took to pose its question."""
    for tool in tools:
        if _tool_name(tool).lower() in QUESTION_TOOLS:
            return "structured_event"
    return "text_fallback" if response.strip() else "no_answer"


def _payload_strings(value: object) -> list[str]:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return _payload_strings(decoded)
    if isinstance(value, Mapping):
        strings: list[str] = []
        for item in value.values():
            strings.extend(_payload_strings(item))
        return strings
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        strings = []
        for item in value:
            strings.extend(_payload_strings(item))
        return strings
    return []


def question_payload(tools: Sequence[object]) -> str:
    """Return scoreable text from structured question tool inputs."""
    strings: list[str] = []
    for tool in tools:
        if _tool_name(tool).lower() not in QUESTION_TOOLS:
            continue
        if not isinstance(tool, Mapping):
            continue
        if "input" in tool:
            strings.extend(_payload_strings(tool["input"]))
        data = tool.get("data")
        if isinstance(data, Mapping):
            for key in ("arguments", "input", "parameters"):
                if key in data:
                    strings.extend(_payload_strings(data[key]))
    return "\n".join(strings)


def structured_tool_model(
    events: Sequence[Mapping[str, object]],
) -> str | None:
    """Return one model id attached to a structured tool turn."""
    models: set[str] = set()
    for event in events:
        if _tool_name(event).lower() not in QUESTION_TOOLS:
            continue
        data = event.get("data")
        if not isinstance(data, Mapping):
            continue
        model = data.get("model")
        if isinstance(model, str):
            models.add(model)
    return models.pop() if len(models) == 1 else None


def traces(
    events: Sequence[Mapping[str, object]],
) -> tuple[list[object], list[object]]:
    """Collect tool and subagent events from both CLI output shapes."""
    tools: list[object] = []
    subagents: list[object] = []
    for event in events:
        event_type = event.get("type")
        if event_type in {"tool.execution_start", "tool.execution_complete"}:
            tools.append(event)
        if isinstance(event_type, str) and "subagent" in event_type.lower():
            subagents.append(event)
        message = event.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    tools.append(block)
                    if block.get("name") in {"Agent", "Task"}:
                        subagents.append(block)
    return tools, subagents


def runtime_failure_record(
    harness: str,
    command: list[str],
    *,
    exit_code: int | None,
    error: str,
    raw_output: str = "",
    stderr: str = "",
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
        "stderr": stderr,
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
