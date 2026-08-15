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
    2 = Block (no model, no definition file, or payload exceeds 2 MiB)

Malformed input within the payload limit fails open by design. Payload
overflow fails closed before parsing. Copilot CLI treats a PreToolUse hook
crash as deny-all for the session (#4672), so an infrastructure failure must
never outrank the guard's own policy. This gate bounds model spend; it is not
a security boundary, so allow-on-broken-input is the cheaper error.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_MAX_STDIN_BYTES = 2 * 1024 * 1024
_SUBAGENT_TOOLS = frozenset({"Agent", "Task", "task"})
_ESCAPE_HATCH_ENV = "CLAUDE_CODE_SUBAGENT_MODEL"
_EMPTY_MODEL_VALUES = frozenset({"", "null", "none", "~", '""', "''"})
_NON_STRING_MODEL_VALUES = frozenset({"false", "no", "off", "on", "true", "yes"})
_UNQUOTED_MODEL_RE = re.compile(r"[A-Za-z][A-Za-z0-9._ /()+-]*")


def _user_root(home: Path, *, copilot: bool) -> Path:
    variable = "COPILOT_HOME" if copilot else "CLAUDE_CONFIG_DIR"
    default = ".copilot" if copilot else ".claude"
    configured = os.environ.get(variable, "").strip()
    return Path(configured).expanduser() if configured else home / default


def _plugin_name(root: Path) -> str | None:
    manifest = root / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    name = data.get("name") if isinstance(data, dict) else None
    return name.strip() if isinstance(name, str) and name.strip() else None


def _active_plugin_roots(plugin: str) -> tuple[Path, ...]:
    roots: list[Path] = []
    for variable in ("COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT"):
        configured = os.environ.get(variable, "").strip()
        if not configured:
            continue
        root = Path(configured).expanduser()
        if root not in roots and _plugin_name(root) == plugin:
            roots.append(root)
    return tuple(roots)


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
        active_patterns = (
            (f"agents/{name}.agent.md", f"agents/{name}.md")
            if copilot
            else (f"agents/{name}.md",)
        )
        active_roots = tuple(
            (root, active_patterns) for root in _active_plugin_roots(plugin)
        )
        if copilot:
            return active_roots + (
                (
                    _user_root(home, copilot=True),
                    (
                        f"installed-plugins/*/{plugin}/agents/{name}.agent.md",
                        f"installed-plugins/*/{plugin}/agents/{name}.md",
                    ),
                ),
            )
        return active_roots + (
            (
                _user_root(home, copilot=False),
                (
                    f"plugins/**/{plugin}/agents/{name}.md",
                    f"plugins/**/{plugin}/*/agents/{name}.md",
                ),
            ),
        )
    if copilot:
        return (
            (project / ".github", (f"agents/{name}.agent.md", f"agents/{name}.md")),
            (
                _user_root(home, copilot=True),
                (
                    f"agents/{name}.agent.md",
                    f"agents/{name}.md",
                ),
            ),
        )
    return (
        (project / ".claude", (f"agents/{name}.md",)),
        (_user_root(home, copilot=False), (f"agents/{name}.md",)),
    )


def _model_scalar(value: str) -> str | None:
    """Return a model only when the YAML token is semantically a string."""
    candidate = value.split("#", 1)[0].strip()
    if not candidate:
        return None
    if candidate.startswith('"'):
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            return None
        return parsed if isinstance(parsed, str) and parsed.strip() else None
    if candidate.startswith("'"):
        if len(candidate) < 2 or not candidate.endswith("'"):
            return None
        parsed = candidate[1:-1].replace("''", "'")
        return parsed if parsed.strip() else None
    normalized = candidate.lower()
    if (
        normalized in _EMPTY_MODEL_VALUES
        or normalized in _NON_STRING_MODEL_VALUES
        or not _UNQUOTED_MODEL_RE.fullmatch(candidate)
    ):
        return None
    return candidate


def _pinned_model(path: Path) -> str | None:
    """Return a nonempty top-level model from YAML frontmatter."""
    try:
        with path.open(encoding="utf-8") as stream:
            if stream.readline().strip() != "---":
                return None
            model: str | None = None
            for line in stream:
                if line.strip() == "---":
                    return model
                if line[:1].isspace():
                    continue
                key, separator, value = line.partition(":")
                if separator and key == "model":
                    if model is not None:
                        return None
                    model = _model_scalar(value)
                    if model is None:
                        return None
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
            definitions = tuple(
                path for path in sorted(root.glob(pattern)) if path.is_file()
            )
            if definitions:
                return all(_pinned_model(path) is not None for path in definitions)
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


def _safe_search_part(value: str) -> bool:
    if value in {"", ".", ".."} or not value.isprintable():
        return False
    return not any(character in value for character in "*?[]/\\:")


def _read_payload() -> object:
    stream = getattr(sys.stdin, "buffer", sys.stdin)
    raw = stream.read(_MAX_STDIN_BYTES + 1)
    if len(raw) > _MAX_STDIN_BYTES:
        raise OverflowError(f"stdin exceeds {_MAX_STDIN_BYTES} bytes")
    return json.loads(raw)


def _is_copilot_payload(payload: dict[str, object]) -> bool:
    """Detect Copilot payloads from guaranteed schema signals.

    Native Copilot uses lowercase ``toolName``/``toolArgs`` while Claude Code
    uses ``tool_name``/``tool_input``.  The Copilot plugin dispatcher uses
    PascalCase ``PreToolUse`` and sets ``COPILOT_PLUGIN_ROOT``, so its
    payloads match the Claude schema but run in a Copilot context.
    """
    if "toolName" in payload and "tool_name" not in payload:
        return True
    return bool(os.environ.get("COPILOT_PLUGIN_ROOT", "").strip())


def _project_root(payload: dict[str, object]) -> Path:
    # Copilot hooks run with cwd set to the repository root by contract.
    # Detect Copilot first so CLAUDE_PROJECT_DIR (a Claude-only variable)
    # cannot redirect Copilot definition lookup.
    if _is_copilot_payload(payload):
        return Path.cwd()
    configured = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    cwd = payload.get("cwd")
    return Path(cwd) if isinstance(cwd, str) and cwd.strip() else Path(".")


def main() -> int:
    try:
        payload = _read_payload()
    except OverflowError as exc:
        print(f"require-subagent-model: {exc}; refusing", file=sys.stderr)
        return 2
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
    plugin_prefix, separator, name = agent.rpartition(":")
    plugin: str | None = plugin_prefix if separator else None
    searchable_parts = (name, plugin) if plugin else (name,)
    searchable = all(_safe_search_part(part) for part in searchable_parts)
    project = _project_root(payload)
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
