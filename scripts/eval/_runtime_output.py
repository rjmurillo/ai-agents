"""Parse machine-readable output from runtime parity subprocesses."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence


class RuntimeOutputError(RuntimeError):
    """A CLI emitted malformed machine-readable output."""


QUESTION_TOOLS = frozenset({"askuserquestion", "ask_user", "askuser", "ask-user"})
AUTH_HINTS = (
    "authentication",
    "not logged in",
    "please run /login",
    "sign in",
    "unauthorized",
)


def claude_result(
    events: Sequence[Mapping[str, object]],
) -> tuple[str, str | None]:
    """Return Claude's final answer and resolved model."""
    model: str | None = None
    response = ""
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init":
            value = event.get("model")
            model = value if isinstance(value, str) else model
        if event.get("type") == "result" and isinstance(event.get("result"), str):
            response = str(event["result"]).strip()
    return response, model


def copilot_result(
    events: Sequence[Mapping[str, object]],
) -> tuple[str, str | None]:
    """Return Copilot's final answer and its attributable model."""
    chunks: list[str] = []
    models: list[str | None] = []
    for event in events:
        if event.get("type") != "assistant.message":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        content = data.get("content")
        model = data.get("model")
        if isinstance(content, str) and content.strip():
            chunks.append(content.strip())
            models.append(model if isinstance(model, str) else None)
    if not chunks:
        return "", None
    attributed = set(models)
    if len(attributed) == 1 and None not in attributed:
        return "\n".join(chunks), models[-1]
    return "\n".join(chunks), None


def failure_code(run: subprocess.CompletedProcess[str]) -> int:
    """Map an unsuccessful runtime process to the public exit contract."""
    text = f"{run.stdout}\n{run.stderr}".lower()
    return 4 if any(hint in text for hint in AUTH_HINTS) else 3


def runtime_error(
    run: subprocess.CompletedProcess[str],
    mechanism: str,
    resolved_model: str | None,
) -> str | None:
    """Explain why a runtime record failed closed."""
    if run.returncode != 0:
        return run.stderr.strip() or f"runtime exited with code {run.returncode}"
    if mechanism == "no_answer":
        return "runtime returned no answer"
    if not resolved_model:
        return "runtime answer has no attributable model"
    return None


def comparison_verdict(
    claude: Mapping[str, object],
    copilot: Mapping[str, object],
    model: str,
) -> str | None:
    """Return the parity failure shared by one completed fixture pair."""
    if (
        claude["resolved_model"] != model
        or copilot["resolved_model"] != model
        or claude["resolved_model"] != copilot["resolved_model"]
    ):
        return "FAIL_MODEL_MISMATCH"
    if claude["question_mechanism"] != copilot["question_mechanism"]:
        return "FAIL_QUESTION_MECHANISM_MISMATCH"
    if not claude["passed"] or not copilot["passed"]:
        return "FAIL"
    return None


def accumulate_verdict(current: str, incoming: str) -> str:
    """Keep the most specific behavioral failure across all fixtures."""
    priority = {
        "PASS": 0,
        "FAIL": 1,
        "FAIL_QUESTION_MECHANISM_MISMATCH": 2,
    }
    return incoming if priority[incoming] > priority[current] else current


def redacted_argv(argv: Sequence[str], harness: str) -> list[str]:
    """Replace the fixture prompt before recording a runtime command."""
    redacted = list(argv)
    prompt_flag = "--print" if harness == "claude" else "--prompt"
    redacted[redacted.index(prompt_flag) + 1] = "<fixture-prompt>"
    return redacted


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
        "provenance": ("Claude runtime" if harness == "claude" else "Copilot runtime"),
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
            raise RuntimeOutputError(f"runtime output line {line_number} must be a JSON object")
        events.append(event)
    return events
