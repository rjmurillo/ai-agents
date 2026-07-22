"""Copilot hook output policies and protocol translation."""

from __future__ import annotations

import json
import sys

_BEHAVIOR_BY_DECISION = {
    "approve": "allow",
    "deny": "deny",
}
_ADDITIONAL_CONTEXT_EVENTS = frozenset(
    {
        "Notification",
        "PostToolUse",
        "SubagentStart",
        "notification",
        "postToolUse",
        "subagentStart",
    }
)
_DISCARD_OUTPUT_EVENTS = frozenset(
    {
        "PreCompact",
        "SessionStart",
        "UserPromptSubmit",
        "UserPromptSubmitted",
        "preCompact",
        "sessionStart",
        "userPromptSubmit",
        "userPromptSubmitted",
    }
)
OUTPUT_POLICIES = frozenset(
    {"additional_context", "discard", "passthrough", "stderr"}
)


def observe_output_policy(event: str) -> str:
    """Return the documented Copilot output policy for an observe event."""
    if event in _ADDITIONAL_CONTEXT_EVENTS:
        return "additional_context"
    if event in _DISCARD_OUTPUT_EVENTS:
        return "discard"
    return "stderr"


def record_discarded_observer_output(
    name: str,
    raw_stdout: str,
    raw_stderr: str,
    event: str,
    exit_code: int,
) -> bool:
    """Report suppressed stderr without exposing its untrusted content."""
    has_stdout = bool(raw_stdout.strip())
    has_stderr = bool(raw_stderr.strip())
    if has_stderr:
        payload = {
            "guard": "hook-dispatch",
            "code": "E_OBSERVER_STDERR",
            "outcome": "stderr_discarded",
            "reason": "observer_emitted_stderr",
            "event": event,
            "shim": name,
            "exit_code": exit_code,
        }
        print(
            f"EVENT={json.dumps(payload, separators=(',', ':'))}",
            file=sys.stderr,
        )
    return has_stdout or has_stderr


def emit_observer_output(
    outputs: list[tuple[str, str]],
    output_policy: str,
    event: str,
) -> None:
    """Emit one host-compatible observer result."""
    if output_policy == "additional_context":
        if outputs:
            context = "\n\n".join(text for _, text in outputs)
            print(json.dumps({"additionalContext": context}))
        return

    if output_policy == "discard":
        for name, _ in outputs:
            print(
                f"hook-dispatch: {name} stdout discarded; stderr discarded; "
                f"{event} hook output is not trusted model context",
                file=sys.stderr,
            )
        return

    if output_policy == "stderr":
        for name, text in outputs:
            print(
                f"hook-dispatch: {name} stdout redirected; "
                "no documented Copilot context output field",
                file=sys.stderr,
            )
            print(text, file=sys.stderr)


def copilot_permission_response(
    raw_stdout: str,
    name: str,
) -> dict[str, object] | None:
    """Translate one canonical Claude permission decision to Copilot fields."""
    if not raw_stdout.strip():
        return None
    decision_text = raw_stdout.strip()
    try:
        decision, end = json.JSONDecoder().raw_decode(decision_text)
    except json.JSONDecodeError as exc:
        print(
            f"hook-dispatch: permission shim {name} emitted malformed JSON: {exc}",
            file=sys.stderr,
        )
        return None
    if decision_text[end:].strip():
        print(
            f"hook-dispatch: permission shim {name} emitted trailing content; "
            "advise mode accepts exactly one decision",
            file=sys.stderr,
        )
        return None
    if not isinstance(decision, dict):
        print(
            f"hook-dispatch: permission shim {name} emitted a non-object decision",
            file=sys.stderr,
        )
        return None
    decision_value = decision.get("decision")
    if decision_value == "ask":
        return None
    behavior = None
    if isinstance(decision_value, str):
        behavior = _BEHAVIOR_BY_DECISION.get(decision_value)
    reason = decision.get("reason")
    if behavior is None:
        print(
            f"hook-dispatch: permission shim {name} emitted an unrecognized decision",
            file=sys.stderr,
        )
        return None
    if not isinstance(reason, str):
        print(
            f"hook-dispatch: permission shim {name} decision "
            f"{decision_value!r} requires a string reason",
            file=sys.stderr,
        )
        return None
    return {
        "behavior": behavior,
        "message": reason,
        "interrupt": False,
    }
