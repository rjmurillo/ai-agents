#!/usr/bin/env python3
"""Event iteration and orchestration for Copilot CLI hook generation.

Extracted from ``generate_hooks.py`` (issue #2223) so the generator stays
under the file-size taste limit. This module owns the upper layer of the
emission pipeline:

- Per-event handlers (``_iter_hooks``, ``_handle_event_drop``,
  ``_handle_unknown_event``, ``_emit_one_hook``, ``_process_event``).
- The ``generate_hooks`` orchestrator that reads the stanza, walks every
  Claude event, copies scripts, and writes ``hooks.json``.

The script-preparation layer (path resolution, copy, entry building) and the
shared value objects live in :mod:`generate_hooks_emit`; both are re-exported
through ``generate_hooks`` so the public names stay importable from there.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from generate_hooks_emit import (  # noqa: E402
    _DEFAULT_TIMEOUT_SEC,
    GenerateHooksError,
    GenerateHooksResult,
    HookAuditEntry,
    _build_copilot_entry,
    _copy_script,
    _load_claude_settings,
    _read_stanza,
    _relative_script_target,
    _resolve_paths,
    _resolve_script_path,
)
from regen_guard import detect_reason as regen_detect_reason  # noqa: E402
from yaml_loader import ConfigError  # noqa: E402

# --- Driver ---------------------------------------------------------------


def _iter_hooks(groups: list[Any]) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
    """Yield ``(group, hook)`` pairs from a Claude-side groups list.

    Skips entries that are not dicts (defensive against malformed
    ``settings.json``); callers do not need to repeat the ``isinstance``
    check.
    """
    for group in groups:
        if not isinstance(group, dict):
            continue
        for hook in group.get("hooks", []) or []:
            if not isinstance(hook, dict):
                continue
            yield group, hook


def _handle_event_drop(
    claude_event: str,
    groups: list[Any],
    *,
    script_source: Path,
    result: GenerateHooksResult,
) -> None:
    """Record an audit entry per hook for a Claude event in eventDrop."""
    for group, hook in _iter_hooks(groups):
        cmd = hook.get("command", "") or ""
        src = _resolve_script_path(script_source, cmd, claude_event)
        script_rel = (
            str(src.relative_to(script_source))
            if src is not None
            else cmd or "<unknown>"
        )
        result.entries.append(
            HookAuditEntry(
                event_source=claude_event,
                event_target="",
                script=script_rel,
                action="dropped",
                matcher=group.get("matcher"),
                reason=f"event '{claude_event}' in eventDrop",
            )
        )
        result.dropped += 1
        print(
            f"  WARN: dropping {claude_event}/{script_rel} "
            f"(event not supported by Copilot CLI)",
            file=sys.stderr,
        )


def _handle_unknown_event(
    claude_event: str,
    groups: list[Any],
    *,
    result: GenerateHooksResult,
) -> None:
    """Record an audit entry per hook for a Claude event missing from eventRemap.

    Operators can extend the remap config; we emit a WARN per hook
    rather than crashing the build.
    """
    for group, hook in _iter_hooks(groups):
        cmd = hook.get("command", "")
        result.entries.append(
            HookAuditEntry(
                event_source=claude_event,
                event_target="",
                script=str(cmd) or "<unknown>",
                action="dropped",
                matcher=group.get("matcher"),
                reason=f"event '{claude_event}' not in eventRemap",
            )
        )
        result.dropped += 1
        print(
            f"  WARN: skipping unknown Claude event '{claude_event}' "
            f"(not in eventRemap)",
            file=sys.stderr,
        )


def _emit_one_hook(
    *,
    claude_event: str,
    target_event: str,
    group: dict[str, Any],
    hook: dict[str, Any],
    script_source: Path,
    output_scripts: Path,
    what_if: bool,
    result: GenerateHooksResult,
) -> tuple[str, dict[str, Any]] | None:
    """Process one hook: resolve, copy (with shim), build the Copilot entry.

    Returns ``(target_event, entry)`` when a Copilot entry should be
    emitted (covers both newly-written and NO-REGEN-skipped cases),
    or ``None`` when the hook is not a Python script under
    ``.claude/hooks/`` (shell snippet skipped with NOTICE).
    """
    matcher = group.get("matcher")
    cmd = hook.get("command", "") or ""
    timeout = _int_field_or_default(
        hook.get("timeout"), _DEFAULT_TIMEOUT_SEC, "hook.timeout"
    )
    src = _resolve_script_path(script_source, cmd, claude_event)
    if src is None:
        result.entries.append(
            HookAuditEntry(
                event_source=claude_event,
                event_target=target_event,
                script=cmd or "<empty>",
                action="dropped",
                matcher=matcher,
                reason="not a Python script under .claude/hooks/",
            )
        )
        result.dropped += 1
        return None

    script_rel = src.relative_to(script_source)
    matcher_str = matcher if isinstance(matcher, str) and matcher else None
    target = _relative_script_target(
        output_scripts, target_event, src.name, matcher=matcher_str
    )
    script_name = target.name  # post-suffix name used by Copilot entry
    written, reason = _copy_script(
        src, target, matcher=matcher_str, what_if=what_if
    )
    entry = _build_copilot_entry(target_event, script_name, timeout_sec=timeout)
    if not written:
        # NO-REGEN: keep customer-owned script untouched but still emit
        # the Copilot config entry (the whole point of NO-REGEN).
        result.entries.append(
            HookAuditEntry(
                event_source=claude_event,
                event_target=target_event,
                script=str(script_rel),
                action="sentinel-skipped",
                matcher=matcher,
                reason=reason,
            )
        )
        result.sentinel_skipped += 1
        return target_event, entry

    result.entries.append(
        HookAuditEntry(
            event_source=claude_event,
            event_target=target_event,
            script=str(script_rel),
            action="emitted",
            matcher=matcher,
        )
    )
    result.written += 1
    return target_event, entry


def _process_event(
    claude_event: str,
    groups: list[Any],
    *,
    event_remap: dict[str, str],
    event_drop: set[str],
    script_source: Path,
    output_scripts: Path,
    what_if: bool,
    result: GenerateHooksResult,
) -> list[tuple[str, dict[str, Any]]]:
    """Process all entries for one Claude event.

    Dispatches to one of three handlers based on the event's status:
    drop (eventDrop), unknown (not in eventRemap), or emit (normal
    path). Returns ``[(target_event, entry_dict), ...]`` for each
    emitted hook. Side effects: copies scripts; appends to
    ``result.entries``.
    """
    if claude_event in event_drop:
        _handle_event_drop(
            claude_event, groups, script_source=script_source, result=result
        )
        return []

    target_event = event_remap.get(claude_event)
    if not target_event:
        _handle_unknown_event(claude_event, groups, result=result)
        return []

    emitted: list[tuple[str, dict[str, Any]]] = []
    for group, hook in _iter_hooks(groups):
        item = _emit_one_hook(
            claude_event=claude_event,
            target_event=target_event,
            group=group,
            hook=hook,
            script_source=script_source,
            output_scripts=output_scripts,
            what_if=what_if,
            result=result,
        )
        if item is not None:
            emitted.append(item)
    return emitted


def _int_field_or_default(
    value: str | bytes | bytearray | int | float | None,
    default: int,
    field_name: str,
) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise GenerateHooksError(f"{field_name} must be an integer") from exc


def generate_hooks(
    config_path: Path,
    repo_root: Path,
    *,
    what_if: bool = False,
) -> tuple[int, GenerateHooksResult]:
    """Generate Copilot CLI hooks per the artifacts.hooks stanza.

    Returns ``(exit_code, result)`` so callers can inspect the audit
    without re-parsing logs.
    """
    print()
    print("=== Hooks -> Copilot ===")
    print(f"Config: {config_path}")
    print(f"Repo root: {repo_root}")
    print(f"Mode: {'WhatIf' if what_if else 'Generate'}")
    print()

    result = GenerateHooksResult()

    try:
        stanza = _read_stanza(config_path)
    except (ConfigError, GenerateHooksError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2, result

    event_remap_raw = stanza["eventRemap"]
    event_remap: dict[str, str] = {
        str(k): str(v) for k, v in event_remap_raw.items()
    }
    event_drop: set[str] = {
        str(item) for item in (stanza.get("eventDrop") or [])
    }
    try:
        version_field = _int_field_or_default(
            stanza.get("versionField"), 1, "artifacts.hooks.versionField"
        )
    except GenerateHooksError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2, result
    # ADR-068 / #2295: when true, collapse the tool-gating event's per-shim
    # entries into one in-process dispatcher entry. Default false keeps the
    # byte-identical per-shim output for every other platform.
    dispatcher_mode = bool(stanza.get("dispatcher", False))

    try:
        paths = _resolve_paths(repo_root, stanza)
    except GenerateHooksError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2, result

    settings_source = paths["settingsSource"]
    script_source = paths["scriptSource"]
    output_config = paths["outputConfig"]
    output_scripts = paths["outputScripts"]

    if not settings_source.is_file():
        print(f"Error: settingsSource not found: {settings_source}", file=sys.stderr)
        return 1, result
    if not script_source.is_dir():
        print(f"Error: scriptSource not a directory: {script_source}", file=sys.stderr)
        return 1, result

    try:
        hooks_map = _load_claude_settings(settings_source)
    except GenerateHooksError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2, result

    start = time.monotonic()
    print(f"Found {len(hooks_map)} Claude event(s) in {settings_source}")

    # Stable iteration order: alphabetical by Claude event name. Output
    # ordering is independent of dict insertion order.
    out: dict[str, list[dict[str, Any]]] = {}
    for claude_event in sorted(hooks_map.keys()):
        groups = hooks_map.get(claude_event)
        if not isinstance(groups, list):
            print(
                f"  WARN: {claude_event} value is not a list; skipping",
                file=sys.stderr,
            )
            continue
        try:
            emitted = _process_event(
                claude_event,
                groups,
                event_remap=event_remap,
                event_drop=event_drop,
                script_source=script_source,
                output_scripts=output_scripts,
                what_if=what_if,
                result=result,
            )
        except GenerateHooksError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2, result
        for target_event, entry in emitted:
            out.setdefault(target_event, []).append(entry)

    # ADR-068 / #2295: consolidate the tool-gating event to one dispatcher
    # entry, emitting _manifest.json + _dispatch.py next to the shims. The
    # shims stay on disk (the dispatcher runs them in-process); only the
    # hooks.json registration changes.
    if dispatcher_mode and not what_if:
        import generate_dispatcher

        out = generate_dispatcher.consolidate(out, output_scripts)

    # Write hooks.json (overwrite). NO-REGEN on the config file itself
    # protects manual customer edits.
    config_reason = regen_detect_reason(output_config)
    if config_reason is not None:
        print(
            f"  NOTICE: skipped {output_config} (NO-REGEN: {config_reason})"
        )
    else:
        wrapped = {"version": version_field, "hooks": out}
        if not what_if:
            output_config.parent.mkdir(parents=True, exist_ok=True)
            output_config.write_text(
                json.dumps(wrapped, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            print(f"  Would write: {output_config}")

    duration = time.monotonic() - start

    print()
    print("=== Summary ===")
    print(f"Duration: {duration:.2f}s")
    print(f"Written: {result.written}")
    if result.dropped:
        print(f"Dropped: {result.dropped}")
    if result.sentinel_skipped:
        print(f"Skipped (NO-REGEN sentinel): {result.sentinel_skipped}")

    return 0, result
