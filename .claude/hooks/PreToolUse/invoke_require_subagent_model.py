#!/usr/bin/env python3
"""Require an explicit model on sub-agent spawns (issue #4874).

A sub-agent whose type has no definition file with a nonempty ``model:``
pin silently
inherits the session model. On a Fable or Opus session that prices every
general-purpose spawn at session-model cost with nobody deciding it. This
gate denies the spawn unless the call names a model, the agent type has a
model-pinned definition file in the active harness, or the operator set
``CLAUDE_CODE_SUBAGENT_MODEL`` to allow inherit-by-default.

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
_EMPTY_MODEL_VALUES = frozenset({"", "null", "none", "~", '""', "''"})


def _definition_search_space(
    name: str,
    plugin: str | None,
    home: Path,
    project: Path,
    *,
    copilot: bool,
) -> tuple[tuple[Path, tuple[str, ...]], ...]:
    """Glob patterns for model-pinned definitions loaded by one harness."""
    if plugin:
        if copilot:
            return (
                (
                    home / ".copilot",
                    (
                        f"installed-plugins/*/{plugin}/agents/{name}.agent.md",
                        f"installed-plugins/*/{plugin}/agents/{name}.md",
                    ),
                ),
            )
        return (
            (
                home / ".claude",
                (
                    f"plugins/**/{plugin}/agents/{name}.md",
                    f"plugins/**/{plugin}/*/agents/{name}.md",
                ),
            ),
        )
    if copilot:
        return (
            (
                home / ".copilot",
                (
                    f"agents/{name}.agent.md",
                    f"agents/{name}.md",
                ),
            ),
            (project / ".github", (f"agents/{name}.agent.md", f"agents/{name}.md")),
        )
    return (
        (home / ".claude", (f"agents/{name}.md",)),
        (project / ".claude", (f"agents/{name}.md",)),
    )


def _pinned_model(path: Path) -> str | None:
    """Return a nonempty top-level model from YAML frontmatter."""
    try:
        with path.open(encoding="utf-8") as stream:
            if stream.readline().strip() != "---":
                return None
            for line in stream:
                if line.strip() == "---":
                    return None
                if line[:1].isspace():
                    continue
                key, separator, value = line.partition(":")
                if separator and key == "model":
                    model = value.split("#", 1)[0].strip()
                    if model.lower() in _EMPTY_MODEL_VALUES:
                        return None
                    return model
    except (OSError, UnicodeError):
        return None
    return None


def _has_pinned_definition(
    name: str,
    plugin: str | None,
    home: Path,
    project: Path,
    *,
    copilot: bool,
) -> bool:
    for root, patterns in _definition_search_space(
        name,
        plugin,
        home,
        project,
        copilot=copilot,
    ):
        if not root.is_dir():
            continue
        for pattern in patterns:
            for path in root.glob(pattern):
                if path.is_file() and _pinned_model(path) is not None:
                    return True
    return False


def _spawn_arguments(payload: dict[str, object]) -> dict[str, object] | None:
    """Normalize tool arguments across payload spellings.

    Claude and PascalCase Copilot registrations send ``tool_input`` as an
    object. Native camelCase Copilot registrations send ``toolArgs``,
    sometimes as a JSON string.
    """
    args = payload.get("tool_input")
    if args is None:
        args = payload.get("toolArgs")
    if isinstance(args, str):
        args = json.loads(args)
    return args if isinstance(args, dict) else None


def _has_explicit_model(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return value.strip().lower() not in _EMPTY_MODEL_VALUES


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
    if _has_explicit_model(args.get("model")) or os.environ.get(_ESCAPE_HATCH_ENV):
        return 0
    agent = args.get("subagent_type") or args.get("agent_type") or ""
    if not isinstance(agent, str) or not agent:
        return 0
    plugin, separator, name = agent.rpartition(":")
    plugin = plugin if separator else None
    searchable_parts = (name, plugin) if plugin else (name,)
    searchable = all(
        part and not any(ch in part for ch in "*?[]/\\") for part in searchable_parts
    )
    project = Path(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    copilot = (
        tool == "task"
        or "toolName" in payload
        or "toolArgs" in payload
        or bool(os.environ.get("COPILOT_PLUGIN_ROOT"))
    )
    if searchable and _has_pinned_definition(
        name,
        plugin,
        Path.home(),
        project,
        copilot=copilot,
    ):
        return 0
    print(
        f"Sub-agent '{agent}' has no model-pinned definition file and this call "
        "names no model, so it would silently inherit the session model. Pass "
        "model: in the call, add an agent definition with a nonempty model:, or set "
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
        print(
            f"[hook-error] require-subagent-model: fail-open on {exc!r}",
            file=sys.stderr,
        )
        raise SystemExit(0) from exc
