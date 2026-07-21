#!/usr/bin/env python3
"""Event iteration and orchestration for Copilot CLI hook generation.

Extracted from ``generate_hooks.py`` (issue #2223) so the generator stays
under the file-size taste limit. This module owns the upper layer of the
emission pipeline:

- Per-event handlers (``_iter_hooks``, ``_handle_event_drop``,
  ``_handle_unknown_event``, ``_emit_one_hook``, ``_process_event``).
- Companion validation (``_validate_companions``, ``_prevalidate_companions``)
  and copy (``_copy_companions``) for runtime-only files a hook script
  imports but that Copilot never dispatches directly.
- The ``generate_hooks`` orchestrator that reads the stanza, walks every
  Claude event, copies scripts, and writes ``hooks.json``.

The script-preparation layer (path resolution, copy, entry building) and the
shared value objects live in :mod:`generate_hooks_emit`; both are re-exported
through ``generate_hooks`` so the public names stay importable from there.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

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
    _ensure_exact_case_dir,
    _load_claude_settings,
    _read_stanza,
    _relative_script_target,
    _resolve_paths,
    _resolve_script_path,
    _validate_event_name,
    _validate_event_target,
    _validate_matcher,
)
from generate_hooks_expand import _expand_dispatch_groups  # noqa: E402,F401
from generate_hooks_transaction import HookGenerationTransaction  # noqa: E402
from regen_guard import detect_reason as regen_detect_reason  # noqa: E402
from yaml_loader import ConfigError  # noqa: E402

# Files required at runtime by one emitted hook but not dispatched themselves.
# No hook currently declares a companion; the mechanism and its tests stay so a
# future companion can be added without re-plumbing the generator.
_COMPANIONS_BY_OWNER: dict[str, tuple[str, ...]] = {}
_DISPATCHER_ARTIFACT_NAMES = ("_manifest.json", "_dispatch.py", "_bootstrap.py")


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
        script_rel = str(src.relative_to(script_source)) if src is not None else cmd or "<unknown>"
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
            f"  WARN: dropping {claude_event}/{script_rel} (event not supported by Copilot CLI)",
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
            f"  WARN: skipping unknown Claude event '{claude_event}' (not in eventRemap)",
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
    transaction: HookGenerationTransaction,
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
    timeout = _int_field_or_default(hook.get("timeout"), _DEFAULT_TIMEOUT_SEC, "hook.timeout")
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
    target = _relative_script_target(output_scripts, target_event, src.name, matcher=matcher_str)
    script_name = target.name  # post-suffix name used by Copilot entry

    # Source companions and protected output companions were prevalidated
    # across every event before the first write. Stage this owner and its
    # companions together so a copy failure cannot publish only part of the
    # runtime unit.
    written, reason = _copy_hook_group(
        src,
        script_rel,
        target,
        transaction=transaction,
        matcher=matcher_str,
        what_if=what_if,
    )
    entry = _build_copilot_entry(target_event, script_name, timeout_sec=timeout)
    # Internal key consumed by generate_dispatcher.event_matcher_union for
    # host-side matcher emission (#3075); stripped before hooks.json is
    # written on every path.
    entry["claudeMatcher"] = matcher_str
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


def _iter_companions(
    owner_relative_path: Path,
    owner_source: Path,
) -> Iterable[tuple[str, Path]]:
    """Yield ``(companion_name, companion_source)`` declared for this owner.

    Shared lookup used by both :func:`_validate_companions` (existence
    check) and :func:`_copy_companions` (copy), so the two never drift on
    which companions belong to which owner.
    """
    companion_names = _COMPANIONS_BY_OWNER.get(owner_relative_path.as_posix(), ())
    for companion_name in companion_names:
        yield companion_name, owner_source.with_name(companion_name)


def _validate_companions(
    owner_relative_path: Path,
    owner_source: Path,
) -> None:
    """Raise when a companion declared for this owner is missing on disk.

    Called by :func:`_prevalidate_companions` for every owner, across every
    event, before :func:`generate_hooks` writes anything. Also reachable
    transitively through the NO-REGEN skip path, which needs the same
    declaration checked without writing anything.
    """
    for _companion_name, companion_source in _iter_companions(owner_relative_path, owner_source):
        if not companion_source.is_file():
            raise GenerateHooksError(
                "declared runtime companion is missing for "
                f"{owner_relative_path.as_posix()}: {companion_source}"
            )


def _validate_no_regen_output_companions(
    owner_relative_path: Path,
    owner_source: Path,
    target_directory: Path,
) -> None:
    """Require protected owners to retain every runtime companion."""
    for companion_name, _companion_source in _iter_companions(owner_relative_path, owner_source):
        companion_target = target_directory / companion_name
        if not companion_target.is_file():
            raise GenerateHooksError(
                "NO-REGEN owner requires an existing runtime companion for "
                f"{owner_relative_path.as_posix()}: {companion_target}"
            )


def _companion_output_targets(
    owner_relative_path: Path,
    owner_source: Path,
    target_directory: Path,
) -> list[tuple[Path, Path]]:
    """Return source and output paths for one owner's companions."""
    return [
        (companion_source, target_directory / companion_name)
        for companion_name, companion_source in _iter_companions(
            owner_relative_path,
            owner_source,
        )
    ]


def _validate_writable_owner_output_companions(
    owner_relative_path: Path,
    owner_source: Path,
    target_directory: Path,
) -> None:
    """Reject a protected companion whose owner remains writable."""
    for _companion_source, companion_target in _companion_output_targets(
        owner_relative_path,
        owner_source,
        target_directory,
    ):
        companion_reason = regen_detect_reason(companion_target)
        if companion_reason is not None:
            raise GenerateHooksError(
                "runtime companion target is NO-REGEN protected while its "
                f"owner is writable: {companion_target} ({companion_reason})"
            )


def _prevalidate_companions(
    hooks_map: dict[str, Any],
    *,
    event_remap: dict[str, str],
    event_drop: set[str],
    script_source: Path,
    output_scripts: Path,
) -> None:
    """Validate every declared companion for every owner before any write.

    Walks the FULL ``hooks_map`` (every Claude event, every group, every
    hook) up front, before :func:`generate_hooks` starts its per-event
    copy loop, and raises on the first owner whose declared companion
    (:data:`_COMPANIONS_BY_OWNER`) is missing from ``script_source``.

    This must run before ANY owner script or ``hooks.json`` is written.
    Previously, validation ran per-owner inside :func:`_emit_one_hook`
    during the copy loop, which only protected the owner currently being
    processed: an earlier owner in iteration order could already be
    copied to disk by the time a later owner's missing companion aborted
    the run, leaving a half-written owner tree with no matching
    ``hooks.json`` (issue #9, confirmed by QA probe: an early owner with
    a valid companion existed on disk after a run that failed on a later
    owner's missing companion). Hoisting validation to one pass over
    every owner, completed before the write loop begins, closes that
    gap: a missing companion anywhere fails the whole run before the
    first byte of output exists.

    Only owners the write loop would actually reach are checked here:
    events in ``eventDrop``, absent from ``event_remap``, or mapped to
    an empty/falsey target are skipped (they never reach
    :func:`_emit_one_hook` -- :func:`_process_event` uses
    ``event_remap.get(claude_event)`` and skips via
    :func:`_handle_unknown_event` whenever that lookup is falsey, not
    only when the key is absent), and commands that do not resolve to a
    Python script under ``script_source`` are skipped too
    (:func:`_resolve_script_path` returns ``None`` for those, matching
    the ``src is None`` early-return in :func:`_emit_one_hook`). This
    keeps prevalidation's notion of "an owner that will be processed"
    identical to the write loop's, so no owner is checked here that
    would not otherwise be copied, and vice versa.
    """
    for claude_event in sorted(hooks_map.keys()):
        if claude_event in event_drop or not event_remap.get(claude_event):
            continue
        groups = hooks_map.get(claude_event)
        if not isinstance(groups, list):
            continue
        target_event = event_remap[claude_event]
        for group, hook in _iter_hooks(groups):
            cmd = hook.get("command", "") or ""
            src = _resolve_script_path(script_source, cmd, claude_event)
            if src is None:
                continue
            script_rel = src.relative_to(script_source)
            _validate_companions(script_rel, src)
            matcher = group.get("matcher")
            matcher_str = matcher if isinstance(matcher, str) and matcher else None
            target = _relative_script_target(
                output_scripts,
                target_event,
                src.name,
                matcher=matcher_str,
            )
            owner_reason = regen_detect_reason(target)
            if owner_reason is not None:
                _validate_no_regen_output_companions(
                    script_rel,
                    src,
                    target.parent,
                )
            else:
                _validate_writable_owner_output_companions(
                    script_rel,
                    src,
                    target.parent,
                )


def _stage_script(
    source: Path,
    target_directory: Path,
    transaction: HookGenerationTransaction,
    *,
    matcher: str | None,
) -> Path:
    """Render one script to a sibling stage file without publishing it."""
    staged: Path = transaction.new_stage_path(target_directory)
    written, reason = _copy_script(
        source,
        staged,
        matcher=matcher,
        what_if=False,
    )
    if not written:
        raise GenerateHooksError(
            f"unexpected NO-REGEN sentinel in staging path: {staged} ({reason})"
        )
    shutil.copystat(source, staged, follow_symlinks=False)
    return staged


def _copy_hook_group(
    owner_source: Path,
    owner_relative_path: Path,
    owner_target: Path,
    transaction: HookGenerationTransaction,
    *,
    matcher: str | None,
    what_if: bool,
) -> tuple[bool, str]:
    """Stage one owner group and publish it through the run transaction."""
    owner_reason = regen_detect_reason(owner_target)
    if owner_reason is not None:
        return False, f"NO-REGEN: {owner_reason}"

    companion_targets = _companion_output_targets(
        owner_relative_path,
        owner_source,
        owner_target.parent,
    )
    _validate_writable_owner_output_companions(
        owner_relative_path,
        owner_source,
        owner_target.parent,
    )
    if matcher:
        _validate_matcher(matcher)
    if what_if:
        return True, ""

    _ensure_exact_case_dir(owner_target.parent)
    try:
        staged_owner = _stage_script(
            owner_source,
            owner_target.parent,
            transaction,
            matcher=matcher,
        )
        staged_companions = [
            (
                _stage_script(
                    companion_source,
                    owner_target.parent,
                    transaction,
                    matcher=None,
                ),
                companion_target,
            )
            for companion_source, companion_target in companion_targets
        ]
        transaction.publish_many([*staged_companions, (staged_owner, owner_target)])
    except OSError as exc:
        raise GenerateHooksError(
            f"failed to stage or publish hook group for {owner_relative_path}: {exc}"
        ) from exc
    return True, ""


def _process_event(
    claude_event: str,
    groups: list[Any],
    *,
    event_remap: dict[str, str],
    event_drop: set[str],
    script_source: Path,
    output_scripts: Path,
    transaction: HookGenerationTransaction,
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
        _handle_event_drop(claude_event, groups, script_source=script_source, result=result)
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
            transaction=transaction,
            what_if=what_if,
            result=result,
        )
        if item is not None:
            emitted.append(item)
    return emitted


def _int_field_or_default(
    value: str | int | None,
    default: int,
    field_name: str,
) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise GenerateHooksError(f"{field_name} must be a positive integer")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped.isascii() or not stripped.isdecimal():
            raise GenerateHooksError(f"{field_name} must be a positive integer")
        parsed = int(stripped)
    else:
        raise GenerateHooksError(f"{field_name} must be a positive integer")
    if parsed <= 0:
        raise GenerateHooksError(f"{field_name} must be a positive integer")
    return parsed


def _dispatcher_artifact_targets(
    out: dict[str, list[dict[str, Any]]],
    output_scripts: Path,
) -> list[Path]:
    """Return every file the dispatcher consolidation may overwrite."""
    return [output_scripts / event / name for event in out for name in _DISPATCHER_ARTIFACT_NAMES]


def _has_dispatchable_hook(
    groups: list[Any],
    script_source: Path,
    claude_event: str,
) -> bool:
    """Return whether normal emission would produce a Python hook entry."""
    return any(
        _resolve_script_path(
            script_source,
            hook.get("command", "") or "",
            claude_event,
        )
        is not None
        for _group, hook in _iter_hooks(groups)
    )


def _dispatcher_candidate_artifact_targets(
    hooks_map: dict[str, Any],
    *,
    event_remap: dict[str, str],
    event_drop: set[str],
    script_source: Path,
    output_scripts: Path,
) -> list[Path]:
    """Return dispatcher targets that valid event processing may produce."""
    target_events = {
        target_event
        for claude_event, groups in hooks_map.items()
        if claude_event not in event_drop
        if (target_event := event_remap.get(claude_event))
        if isinstance(groups, list)
        if _has_dispatchable_hook(groups, script_source, claude_event)
    }
    return [
        output_scripts / event / name
        for event in sorted(target_events)
        for name in _DISPATCHER_ARTIFACT_NAMES
    ]


def _validate_dispatcher_artifact_targets(targets: Iterable[Path]) -> None:
    """Reject dispatcher generation when any output is NO-REGEN protected."""
    for target in targets:
        reason = regen_detect_reason(target)
        if reason is not None:
            raise GenerateHooksError(
                f"dispatcher artifact is NO-REGEN protected: {target} ({reason})"
            )


def _stage_dispatcher_artifacts(
    out: dict[str, list[dict[str, Any]]],
    output_scripts: Path,
    transaction: HookGenerationTransaction,
) -> dict[str, list[dict[str, Any]]]:
    """Generate dispatcher files off-tree, then publish them transactionally."""
    import generate_dispatcher

    stage_root = transaction.new_stage_directory(output_scripts.parent)
    for event in out:
        try:
            generate_dispatcher.validate_event_name(event)
        except ValueError as exc:
            raise GenerateHooksError(f"dispatcher event path validation failed: {exc}") from exc
        (stage_root / event).mkdir(parents=True, exist_ok=True)
    try:
        consolidated = generate_dispatcher.consolidate(out, stage_root)
    except ValueError as exc:
        raise GenerateHooksError(f"dispatcher configuration invalid: {exc}") from exc
    try:
        hooks_root = output_scripts.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise GenerateHooksError(f"dispatcher cleanup path validation failed: {exc}") from exc
    stale_targets: list[Path] = []
    direct_events: set[str] = set()
    for event in sorted(out):
        manifest_path = stage_root / event / "_manifest.json"
        if not manifest_path.is_file():
            direct_events.add(event)
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        shim_names = manifest.get("shims")
        if not isinstance(shim_names, list) or not all(
            isinstance(name, str) for name in shim_names
        ):
            raise GenerateHooksError(
                f"generated dispatcher manifest has invalid shims: {manifest_path}"
            )
        published_event_dir = output_scripts / event
        try:
            stale_targets.extend(
                generate_dispatcher.find_stale_matcher_shims(
                    published_event_dir,
                    shim_names,
                    hooks_root=hooks_root,
                )
            )
        except ValueError as exc:
            raise GenerateHooksError(f"dispatcher cleanup path validation failed: {exc}") from exc
    stale_targets.extend(
        generate_dispatcher.find_owned_dispatcher_core_artifacts(
            output_scripts,
            direct_events,
        )
    )
    publish_pairs: list[tuple[Path, Path]] = []
    for generated in _dispatcher_artifact_targets(consolidated, stage_root):
        if not generated.is_file():
            continue
        target = output_scripts / generated.relative_to(stage_root)
        staged = transaction.new_stage_path(target.parent)
        shutil.copy2(generated, staged)
        publish_pairs.append((staged, target))
    transaction.delete_many(stale_targets)
    transaction.publish_many(publish_pairs)
    return cast(dict[str, list[dict[str, Any]]], consolidated)


def _stage_orphan_event_cleanup(
    out: dict[str, list[dict[str, Any]]],
    script_source: Path,
    output_scripts: Path,
    transaction: HookGenerationTransaction,
    *,
    what_if: bool,
) -> list[Path]:
    """Stage deletion of ownership-proven generated files for inactive events."""
    import generate_dispatcher

    targets, directories = cast(
        tuple[list[Path], list[Path]],
        generate_dispatcher.find_owned_orphan_artifacts(
            output_scripts,
            set(out),
            source_hooks=script_source,
        ),
    )
    if what_if:
        for target in targets:
            print(f"  Would remove generated orphan: {target}")
        return []
    transaction.delete_many(targets)
    return directories


def _stage_dispatcher_changes(
    out: dict[str, list[dict[str, Any]]],
    script_source: Path,
    output_scripts: Path,
    transaction: HookGenerationTransaction,
    *,
    what_if: bool,
) -> tuple[dict[str, list[dict[str, Any]]], list[Path]]:
    """Stage dispatcher publication and ownership-proven orphan cleanup."""
    try:
        if not what_if:
            _validate_dispatcher_artifact_targets(_dispatcher_artifact_targets(out, output_scripts))
            out = _stage_dispatcher_artifacts(out, output_scripts, transaction)
    except OSError as exc:
        raise OSError(f"dispatcher generation failed: {exc}") from exc

    try:
        directories = _stage_orphan_event_cleanup(
            out,
            script_source,
            output_scripts,
            transaction,
            what_if=what_if,
        )
    except OSError as exc:
        raise OSError(f"orphan hook cleanup failed: {exc}") from exc
    return out, directories


def _remove_empty_orphan_directories(directories: list[Path]) -> None:
    """Remove only empty orphan directories, deepest first, after commit."""
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        try:
            directory.rmdir()
        except FileNotFoundError:
            continue
        except OSError as exc:
            if directory.exists():
                print(f"  NOTICE: preserved non-empty orphan directory {directory}: {exc}")


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
    try:
        event_remap: dict[str, str] = {}
        for k, v in event_remap_raw.items():
            # Reject non-string keys/values BEFORE any str() coercion. YAML
            # parses `PreToolUse: false` to the bool False; a silent str(False)
            # would yield the literal event name "False", which passes the
            # alphanumeric event-name allowlist and misroutes the PreToolUse
            # security hooks to a bogus hooks/False/ directory the host never
            # fires (fail-open). A null, boolean, or numeric scalar here is a
            # config error, not a remap to its stringified form (#3212 family,
            # CWE-704 incorrect type conversion).
            if not isinstance(k, str) or not isinstance(v, str):
                raise GenerateHooksError(
                    "eventRemap keys and values must be strings; a non-string "
                    "YAML scalar (null 'PreToolUse:', boolean "
                    "'PreToolUse: false', or number) is a config error, not a "
                    "silent remap to its stringified form such as the literal "
                    f"event 'None', 'False', or 'True': {k!r}: {v!r}"
                )
            event_remap[_validate_event_name(k)] = _validate_event_target(v)
        # eventDrop carries the same non-string footgun: a bool `false` would
        # coerce to a bogus drop of the literal event "False". Fail closed.
        event_drop: set[str] = set()
        for item in stanza.get("eventDrop") or []:
            if not isinstance(item, str):
                raise GenerateHooksError(
                    "eventDrop entries must be strings; a non-string YAML "
                    "scalar (e.g. boolean 'false') is a config error, not a "
                    f"drop of the literal event 'False': {item!r}"
                )
            # Same allowlist as eventRemap keys: a drop entry names a Claude
            # event, so validate it against _EVENT_NAME_RE to keep the
            # fail-closed posture consistent. Drop values only feed set
            # membership today, but validating here means a future path that
            # renders them is already guarded (#3212, #3213).
            event_drop.add(_validate_event_name(item))
    except GenerateHooksError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2, result
    try:
        version_field = _int_field_or_default(
            stanza.get("versionField"), 1, "artifacts.hooks.versionField"
        )
    except GenerateHooksError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2, result
    # ADR-068 / #2295: when true, collapse classified events' per-shim entries
    # into one in-process dispatcher entry. Default false keeps direct per-shim
    # registrations. Lifecycle events with repository prose remain shell-silent.
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
    config_reason = regen_detect_reason(output_config)
    if config_reason is not None:
        print(
            "  NOTICE: preserved generated hook artifact set because "
            f"{output_config} is NO-REGEN protected: {config_reason}"
        )
        return 0, result

    try:
        hooks_map = _load_claude_settings(settings_source)
        hooks_map = _expand_dispatch_groups(hooks_map, script_source)
    except GenerateHooksError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2, result

    # Validate every declared companion for every owner, across every
    # event, BEFORE any owner script or hooks.json is written (#9). See
    # :func:`_prevalidate_companions` for why this must be a dedicated
    # pass rather than validation inline in the copy loop below.
    try:
        _prevalidate_companions(
            hooks_map,
            event_remap=event_remap,
            event_drop=event_drop,
            script_source=script_source,
            output_scripts=output_scripts,
        )
    except GenerateHooksError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2, result
    if dispatcher_mode and not what_if:
        try:
            _validate_dispatcher_artifact_targets(
                _dispatcher_candidate_artifact_targets(
                    hooks_map,
                    event_remap=event_remap,
                    event_drop=event_drop,
                    script_source=script_source,
                    output_scripts=output_scripts,
                )
            )
        except GenerateHooksError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2, result

    start = time.monotonic()
    print(f"Found {len(hooks_map)} Claude event(s) in {settings_source}")

    try:
        transaction = HookGenerationTransaction(output_scripts)
    except OSError as exc:
        print(f"Error: could not acquire hook generation lock: {exc}", file=sys.stderr)
        return 1, result

    committed = False
    orphan_directories: list[Path] = []
    try:
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
                    transaction=transaction,
                    what_if=what_if,
                    result=result,
                )
            except GenerateHooksError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 2, result
            for target_event, entry in emitted:
                out.setdefault(target_event, []).append(entry)

        # ADR-068 / #2295: consolidate safely mergeable events to one dispatcher
        # entry and keep structured decision events direct. Consolidated shims
        # stay on disk and run in-process; only hooks.json registration changes.
        if dispatcher_mode:
            try:
                out, orphan_directories = _stage_dispatcher_changes(
                    out,
                    script_source,
                    output_scripts,
                    transaction,
                    what_if=what_if,
                )
            except GenerateHooksError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 2, result
            except OSError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1, result

        # Drop the generator-internal matcher key on every path (dispatcher
        # or per-shim) so it never reaches the emitted hooks.json.
        for entries in out.values():
            for entry in entries:
                if isinstance(entry, dict):
                    entry.pop("claudeMatcher", None)

        # Write hooks.json through the same transaction as every generated
        # script. Recheck NO-REGEN immediately before publication so a sentinel
        # created during generation rolls back the entire artifact set.
        config_reason = regen_detect_reason(output_config)
        if config_reason is not None:
            print(
                "  NOTICE: preserved generated hook artifact set because "
                f"{output_config} is NO-REGEN protected: {config_reason}"
            )
            return 0, result
        wrapped = {"version": version_field, "hooks": out}
        if not what_if:
            output_config.parent.mkdir(parents=True, exist_ok=True)
            staged_config = transaction.new_stage_path(output_config.parent)
            try:
                staged_config.write_text(
                    json.dumps(wrapped, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                staged_config.chmod(0o644)
                transaction.publish_many([(staged_config, output_config)])
            except OSError as exc:
                print(
                    f"Error: hooks.json generation failed: {exc}",
                    file=sys.stderr,
                )
                return 1, result
        else:
            print(f"  Would write: {output_config}")

        cleanup_errors = transaction.commit()
        committed = True
        for cleanup_error in cleanup_errors:
            print(f"  WARN: {cleanup_error}", file=sys.stderr)
        _remove_empty_orphan_directories(orphan_directories)
    finally:
        if not committed:
            for rollback_error in transaction.rollback():
                print(
                    f"  WARN: generation rollback failed: {rollback_error}",
                    file=sys.stderr,
                )
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
