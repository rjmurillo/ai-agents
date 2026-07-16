#!/usr/bin/env python3
"""Claude-side dispatch-group expansion for Copilot hook generation (#3075).

``.claude/settings.json`` registers ONE ``invoke_dispatch_claude.py`` process per
(event, matcher) group to cut per-hook spawn cost on the Claude Code side.
Copilot CLI has its own consolidation (ADR-068 dispatcher), so the
generator expands each dispatch registration back to the per-hook entries
recorded in ``.claude/hooks/dispatch_groups.json`` before emission. The
expanded entries reproduce the pre-consolidation command, timeout, and
statusMessage values, so the generated Copilot tree is unchanged by the
Claude-side consolidation. Extracted from ``generate_hooks_events.py`` to
keep that module under the file-size taste limit.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from generate_hooks_emit import GenerateHooksError  # noqa: E402

_DISPATCH_COMMAND_RE = re.compile(
    r"dispatch_claude\.py\"?\s+--group\s+([A-Za-z0-9_-]+)"
)


def _load_dispatch_groups(script_source: Path) -> dict[str, Any]:
    """Read the dispatch-group manifest next to the hook sources."""
    manifest = script_source / "dispatch_groups.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GenerateHooksError(
            f"cannot read dispatch manifest {manifest}: {exc}"
        ) from exc
    except ValueError as exc:
        raise GenerateHooksError(
            f"malformed dispatch manifest {manifest}: {exc}"
        ) from exc
    groups = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(groups, dict):
        raise GenerateHooksError(
            f"dispatch manifest {manifest} has no 'groups' object"
        )
    return groups


def _expanded_hook_entry(shim: dict[str, Any], group_id: str) -> dict[str, Any]:
    """Rebuild one pre-consolidation hook dict from a manifest shim."""
    file_rel = shim.get("file")
    if not isinstance(file_rel, str) or not file_rel:
        raise GenerateHooksError(
            f"dispatch group {group_id!r} has a shim without a 'file'"
        )
    hook: dict[str, Any] = {
        "type": "command",
        "command": f"python3 -u .claude/hooks/{file_rel}",
    }
    if "timeout" in shim:
        hook["timeout"] = shim["timeout"]
    if "statusMessage" in shim:
        hook["statusMessage"] = shim["statusMessage"]
    return hook


def _expand_one_dispatch_group(
    group_id: str,
    claude_event: str,
    registration_matcher: str | None,
    manifest_groups: dict[str, Any],
) -> list[dict[str, Any]]:
    """Expand one dispatcher registration to per-hook settings groups."""
    spec = manifest_groups.get(group_id)
    if not isinstance(spec, dict):
        raise GenerateHooksError(
            f"dispatch group {group_id!r} is not defined in dispatch_groups.json"
        )
    if spec.get("event") != claude_event:
        raise GenerateHooksError(
            f"dispatch group {group_id!r} is registered under {claude_event} "
            f"but the manifest declares event {spec.get('event')!r}"
        )
    partitions: list[tuple[Any, list[dict[str, Any]]]] = []
    for shim in spec.get("shims", []) or []:
        if not isinstance(shim, dict):
            raise GenerateHooksError(
                f"dispatch group {group_id!r} has a non-object shim entry"
            )
        matcher = shim.get("copilotMatcher") or registration_matcher
        hook = _expanded_hook_entry(shim, group_id)
        if partitions and partitions[-1][0] == matcher:
            partitions[-1][1].append(hook)
        else:
            partitions.append((matcher, [hook]))
    expanded: list[dict[str, Any]] = []
    for matcher, hooks in partitions:
        group: dict[str, Any] = {}
        if isinstance(matcher, str) and matcher:
            group["matcher"] = matcher
        group["hooks"] = hooks
        expanded.append(group)
    return expanded


def _expand_dispatch_groups(
    hooks_map: dict[str, Any],
    script_source: Path,
) -> dict[str, Any]:
    """Replace invoke_dispatch_claude.py registrations with their member hooks."""
    manifest_groups: dict[str, Any] | None = None
    expanded_map: dict[str, Any] = {}
    for claude_event, groups in hooks_map.items():
        if not isinstance(groups, list):
            expanded_map[claude_event] = groups
            continue
        new_groups: list[Any] = []
        for group in groups:
            if not isinstance(group, dict):
                new_groups.append(group)
                continue
            hooks = group.get("hooks") or []
            matches = [
                _DISPATCH_COMMAND_RE.search(hook.get("command", "") or "")
                for hook in hooks
                if isinstance(hook, dict)
            ]
            found = [m for m in matches if m is not None]
            if not found:
                new_groups.append(group)
                continue
            if len(hooks) != 1 or len(found) != 1:
                raise GenerateHooksError(
                    "a invoke_dispatch_claude.py registration must be the only hook "
                    f"in its settings group (event {claude_event})"
                )
            if manifest_groups is None:
                manifest_groups = _load_dispatch_groups(script_source)
            new_groups.extend(
                _expand_one_dispatch_group(
                    found[0].group(1),
                    claude_event,
                    group.get("matcher"),
                    manifest_groups,
                )
            )
        expanded_map[claude_event] = new_groups
    return expanded_map
