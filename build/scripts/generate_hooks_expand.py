#!/usr/bin/env python3
"""Claude-side dispatch-group expansion for Copilot hook generation (#3075).

``.claude/settings.json`` registers ONE ``invoke_dispatch_claude.py`` process per
(event, matcher) group to cut per-hook spawn cost on the Claude Code side.
Copilot CLI has its own consolidation (ADR-068 dispatcher), so the
generator expands each dispatch registration back to the per-hook entries
recorded in ``.claude/hooks/dispatch_groups.json`` before emission. The
expanded entries reproduce the pre-consolidation command, timeout, and
statusMessage values, so the generated Copilot tree is unchanged by the
Claude-side consolidation, EXCEPT for a shim whose manifest entry sets
``copilotExclude: true`` (issue #5013): that shim is omitted from the
Copilot expansion outright, while ``invoke_dispatch_claude.py`` still runs
it unchanged on the Claude Code side, because that entry point never reads
``copilotExclude``.

Phase 2 (issue #5013, ADR-085 Decision 7, "Generic field governance") adds
three fail-closed rules to ``copilotExclude`` itself, enforced by
:func:`_copilot_exclude_flag` and :func:`_require_copilot_exclude_governance`
below:

1. Strict boolean validation (governance item 1). Quoted verbatim from
   ``.agents/architecture/ADR-085-cross-harness-permission-surface-asymmetry.md``,
   Decision 7: "The generator rejects any `copilotExclude` value that is
   not literally `true` or `false`; a truthy non-boolean value such as
   `1`, `"true"`, or `null` fails generation rather than silently
   including or excluding the shim."
2. Plugin surface required (governance item 2, "Plugin surface named"):
   ``copilotExclude: true`` is only accepted on a dispatch group that
   declares ``surface: plugin``. A group outside the generated Copilot
   plugin surface has no Copilot generation path to exclude a shim from.
3. Issue and decision metadata (governance items 3-4): ``copilotExclude:
   true`` requires traceable ``copilotExcludeIssue`` and
   ``copilotExcludeDecision`` string fields naming the authorizing issue and
   the ADR that owns the security judgment.

Extracted from ``generate_hooks_events.py`` to keep that module under the
file-size taste limit.
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
_ISSUE_REFERENCE_RE = re.compile(r"#\d+")
_ADR_REFERENCE_RE = re.compile(r"ADR-\d+")

# The only dispatch-group surface a shim may be excluded from Copilot
# generation on (ADR-085 Decision 7, governance item 2). Every group in the
# committed manifest that ISN'T this surface (e.g. "sessionstart-1-
# context_loader", which sets no surface at all) has no Copilot generation
# path to exclude a shim from in the first place.
_EXCLUDABLE_SURFACE = "plugin"


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


def _copilot_exclude_flag(shim: dict[str, Any], group_id: str) -> bool:
    """Return the strict-boolean ``copilotExclude`` flag for one shim.

    An absent key means ``False``. A PRESENT key must be literally ``True``
    or ``False``: Python's ``bool`` is an ``int`` subclass, so this checks
    ``isinstance(raw, bool)`` rather than truthiness, which is the only way
    to accept ``True``/``False`` while rejecting ``1``/``0`` (and every
    string, ``None``, list, or object) as required by ADR-085 Decision 7,
    generic field governance item 1 (quoted in the module docstring).
    """
    if "copilotExclude" not in shim:
        return False
    raw = shim["copilotExclude"]
    if not isinstance(raw, bool):
        file_rel = shim.get("file", "<unknown>")
        raise GenerateHooksError(
            f"dispatch group {group_id!r} shim {file_rel!r} has "
            f"copilotExclude={raw!r} ({type(raw).__name__}); it must be a "
            "strict boolean, not a string, number, null, list, or object "
            "(issue #5013, ADR-085 Decision 7 governance item 1)"
        )
    return raw


def _require_exclude_reference(
    shim: dict[str, Any],
    field: str,
    group_id: str,
    file_rel: str,
) -> None:
    """Raise unless ``shim[field]`` names a traceable issue or ADR reference.

    Backs governance items 3 (issue metadata) and 4 (decision metadata):
    both name a record the ADR itself must also carry, so a missing,
    blank, malformed, or non-string value here is a manifest authoring
    error, not an optional annotation.
    """
    value = shim.get(field)
    if not isinstance(value, str) or not value.strip():
        raise GenerateHooksError(
            f"dispatch group {group_id!r} shim {file_rel!r} sets "
            f"copilotExclude=true but {field!r} is missing, blank, or not a "
            "string; copilotExcludeIssue and copilotExcludeDecision must "
            "both be non-empty strings (issue #5013, ADR-085 Decision 7 "
            "governance items 3-4)"
        )
    trimmed = value.strip()
    pattern = _ISSUE_REFERENCE_RE if field == "copilotExcludeIssue" else _ADR_REFERENCE_RE
    example = "#5013" if field == "copilotExcludeIssue" else "ADR-085"
    if pattern.fullmatch(trimmed) is None:
        raise GenerateHooksError(
            f"dispatch group {group_id!r} shim {file_rel!r} sets "
            f"copilotExclude=true but {field!r}={value!r} is not a traceable "
            f"reference; expected {example!r} format (issue #5013, "
            "ADR-085 Decision 7 governance items 3-4)"
        )


def _require_copilot_exclude_governance(
    shim: dict[str, Any],
    spec: dict[str, Any],
    group_id: str,
) -> None:
    """Enforce ADR-085 Decision 7's rules for one ``copilotExclude: true`` shim.

    Order mirrors the ADR's own governance-item numbering: surface (item 2),
    then issue metadata (item 3), then decision metadata (item 4). Item 1
    (strict boolean) is enforced by :func:`_copilot_exclude_flag` before this
    function ever runs.
    """
    file_rel = shim.get("file", "<unknown>")
    surface = spec.get("surface")
    if surface != _EXCLUDABLE_SURFACE:
        raise GenerateHooksError(
            f"dispatch group {group_id!r} shim {file_rel!r} sets "
            f"copilotExclude=true but the group's surface is {surface!r}; "
            f"exclusion is only allowed on a {_EXCLUDABLE_SURFACE!r}-surface "
            "group (issue #5013, ADR-085 Decision 7 governance item 2)"
        )
    for field in ("copilotExcludeIssue", "copilotExcludeDecision"):
        _require_exclude_reference(shim, field, group_id, file_rel)


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
        if _copilot_exclude_flag(shim, group_id):
            # Issue #5013: the push-pr identity guard registered on the bare
            # Bash matcher denied unrelated commands after a child-process
            # timeout. Omit any copilotExclude shim from Copilot expansion
            # entirely; invoke_dispatch_claude.py never reads this field, so
            # the Claude Code gate keeps running the shim unchanged.
            _require_copilot_exclude_governance(shim, spec, group_id)
            continue
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
