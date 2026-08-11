#!/usr/bin/env python3
"""Require an explicit model on sub-agent spawns (issue #4874).

A sub-agent whose type has no definition file to pin ``model:`` silently
inherits the session model. On a Fable or Opus session that prices every
general-purpose spawn at session-model cost with nobody deciding it. This
gate denies the spawn unless the call names a model, the agent type has a
definition file somewhere the harness loads agents from, or the operator
set ``CLAUDE_CODE_SUBAGENT_MODEL`` to allow inherit-by-default.

Customer value: no silent session-model inheritance for sub-agents on
either harness.

Cross-harness payload contract:
    Claude Code registers the spawn tool as ``Agent`` (``Task`` before the
    rename) and sends ``tool_input.subagent_type`` plus optional
    ``tool_input.model``. Copilot CLI's runtime tool is ``task`` (Claude
    name ``Agent``); its args carry ``agent_type`` and optional ``model``,
    observed in a real session log (Copilot CLI 1.0.79, 2026-08-06,
    ``events.jsonl`` ``toolRequests``). Native camelCase registrations send
    ``toolName``/``toolArgs`` where ``toolArgs`` may be a JSON string.

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (model named, escape hatch set, definition file found,
        unrelated tool, or malformed input)
    2 = Block (no model, no definition file)

Malformed input fails open by design: Copilot CLI treats a PreToolUse hook
crash as deny-all for the session (#4672), so an infrastructure failure
must never outrank the guard's own policy. This gate bounds model spend;
it is not a security boundary, so allow-on-broken-input is the cheaper
error.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_MAX_STDIN_BYTES = 128 * 1024
_SUBAGENT_TOOLS = frozenset({"Agent", "Task", "task"})
_ESCAPE_HATCH_ENV = "CLAUDE_CODE_SUBAGENT_MODEL"


def _definition_search_space(
    name: str, home: Path, project: Path
) -> tuple[tuple[Path, tuple[str, ...]], ...]:
    """Glob patterns per root that can hold an agent definition.

    Covers both harnesses regardless of which one invoked the hook: user
    and project agent dirs, plus each harness's installed-plugin trees.
    """
    return (
        (home / ".claude", (f"agents/{name}.md", f"plugins/**/agents/{name}.md")),
        (project / ".claude", (f"agents/{name}.md",)),
        (
            home / ".copilot",
            (
                f"agents/{name}.agent.md",
                f"agents/{name}.md",
                f"installed-plugins/**/agents/{name}.agent.md",
                f"installed-plugins/**/agents/{name}.md",
            ),
        ),
        (project / ".github", (f"agents/{name}.agent.md", f"agents/{name}.md")),
    )


def _has_definition(name: str, home: Path, project: Path) -> bool:
    for root, patterns in _definition_search_space(name, home, project):
        if not root.is_dir():
            continue
        for pattern in patterns:
            if any(root.glob(pattern)):
                return True
    return False


def _spawn_arguments(payload: dict[str, object]) -> dict[str, object] | None:
    """Normalize tool arguments across payload spellings.

    Claude and PascalCase Copilot registrations send ``tool_input`` as an
    object. Native camelCase Copilot registrations send ``toolArgs``,
    sometimes as a JSON string.
    """
    args = payload.get("tool_input", payload.get("toolArgs"))
    if isinstance(args, str):
        args = json.loads(args)
    return args if isinstance(args, dict) else None


def main() -> int:
    payload = json.loads(sys.stdin.read(_MAX_STDIN_BYTES))
    if not isinstance(payload, dict):
        return 0
    tool = payload.get("tool_name") or payload.get("toolName") or ""
    if tool not in _SUBAGENT_TOOLS:
        return 0
    args = _spawn_arguments(payload)
    if args is None:
        return 0
    if args.get("model") or os.environ.get(_ESCAPE_HATCH_ENV):
        return 0
    agent = args.get("subagent_type") or args.get("agent_type") or ""
    if not isinstance(agent, str) or not agent:
        return 0
    name = agent.rsplit(":", 1)[-1]  # plugin-scoped type: my-plugin:reviewer
    searchable = not any(ch in name for ch in "*?[]/\\")  # glob or path chars spoof the search
    project = Path(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    if searchable and _has_definition(name, Path.home(), project):
        return 0
    print(
        f"Sub-agent '{agent}' has no definition file and this call names no "
        "model, so it would silently inherit the session model. Pass model: "
        "in the call, add an agent definition that pins model:, or set "
        f"{_ESCAPE_HATCH_ENV} to allow inherit-by-default.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        # Mini-ADR: broad catch is the fail-open contract, not sloppiness.
        # Copilot CLI converts any PreToolUse crash into a denial of the
        # tool call (#4672), so an unexpected payload shape or filesystem
        # error must degrade to allow-with-warning, never deny.
        print(f"require-subagent-model: fail-open on {exc!r}", file=sys.stderr)
        raise SystemExit(0) from exc
