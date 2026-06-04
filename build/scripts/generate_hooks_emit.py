#!/usr/bin/env python3
"""Script preparation for Copilot CLI hook generation.

Extracted from ``generate_hooks.py`` (issue #2223) so the generator stays
under the file-size taste limit. This module owns the lowest layer of the
emission pipeline:

- ``GenerateHooksError`` and ``_DEFAULT_TIMEOUT_SEC`` (shared by the rest of
  the pipeline).
- The audit value objects ``HookAuditEntry`` and ``GenerateHooksResult``.
- Config-stanza parsing, path resolution, ``settings.json`` reading, script
  discovery, on-disk copy (with shim injection), and Copilot entry building.

The event-iteration and orchestration layer lives in
:mod:`generate_hooks_events`; both modules are re-exported through
``generate_hooks`` so the public names stay importable from there.
"""

from __future__ import annotations

import hashlib
import json
import re as _re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
import sys  # noqa: E402

if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from generate_hooks_body import inject_shim  # noqa: E402
from regen_guard import detect_reason as regen_detect_reason  # noqa: E402
from yaml_loader import (  # noqa: E402
    load_platform_config,
    validate_relative_path,
)

_DEFAULT_TIMEOUT_SEC = 30


class GenerateHooksError(Exception):
    """Domain error for hook generation."""


@dataclass
class HookAuditEntry:
    """One hook script's outcome, used by tests and audit."""

    event_source: str  # Claude-side event (e.g. PreToolUse)
    event_target: str  # Copilot-side event (e.g. preToolUse) or "" if dropped
    script: str  # relative script path, e.g. PreToolUse/foo.py
    action: str  # "emitted" | "dropped" | "sentinel-skipped"
    matcher: str | None = None
    reason: str = ""


@dataclass
class GenerateHooksResult:
    """Aggregate result for a generation run.

    ``written`` counts emitted entries (one per Claude hook entry that
    survives event mapping); ``dropped`` counts entries whose event was
    in ``eventDrop``; ``sentinel_skipped`` counts target scripts not
    overwritten because of NO-REGEN sentinels.
    """

    written: int = 0
    dropped: int = 0
    sentinel_skipped: int = 0
    entries: list[HookAuditEntry] = field(default_factory=list)


# --- Stanza parsing -------------------------------------------------------


def _read_stanza(config_path: Path) -> dict[str, Any]:
    cfg = load_platform_config(config_path)
    artifacts = cfg.get("artifacts")
    if not isinstance(artifacts, dict):
        raise GenerateHooksError(
            f"{config_path}: missing `artifacts` mapping"
        )
    stanza = artifacts.get("hooks")
    if not isinstance(stanza, dict):
        raise GenerateHooksError(
            f"{config_path}: missing `artifacts.hooks` stanza"
        )
    # Required fields.
    for key in (
        "settingsSource",
        "scriptSource",
        "outputConfig",
        "outputScripts",
        "eventRemap",
    ):
        if key not in stanza:
            raise GenerateHooksError(
                f"{config_path}: artifacts.hooks missing required key `{key}`"
            )
    if not isinstance(stanza["eventRemap"], dict):
        raise GenerateHooksError(
            f"{config_path}: artifacts.hooks.eventRemap must be a mapping"
        )
    drops = stanza.get("eventDrop") or []
    if not isinstance(drops, list):
        raise GenerateHooksError(
            f"{config_path}: artifacts.hooks.eventDrop must be a list"
        )
    return stanza


def _resolve_paths(repo_root: Path, stanza: dict[str, Any]) -> dict[str, Path]:
    """Validate and resolve every path field; reject traversal/absolute."""
    resolved: dict[str, Path] = {}
    for field_name in (
        "settingsSource",
        "scriptSource",
        "outputConfig",
        "outputScripts",
    ):
        value = stanza[field_name]
        errs = validate_relative_path(field_name, value)
        if errs:
            raise GenerateHooksError("; ".join(errs))
        resolved[field_name] = repo_root / value
    return resolved


# --- Settings.json reader -------------------------------------------------


def _load_claude_settings(path: Path) -> dict[str, Any]:
    """Parse ``.claude/settings.json`` and return its ``hooks`` map."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise GenerateHooksError(f"settingsSource missing: {path}") from exc
    except OSError as exc:
        raise GenerateHooksError(f"read error for '{path}': {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GenerateHooksError(
            f"{path}: malformed JSON: {exc}"
        ) from exc
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        raise GenerateHooksError(
            f"{path}: top-level `.hooks` must be an object"
        )
    return hooks


# --- Script discovery and copy -------------------------------------------


def _resolve_script_path(
    script_source: Path, command: str, claude_event: str
) -> Path | None:
    """Map a Claude command string to its source script path.

    The Claude command shape is::

        python3 -u .claude/hooks/<Event>/<script>.py
        python3 -u .claude/hooks/<script>.py        (flat layout)

    Returns ``None`` when the command does not point at a script under
    ``.claude/hooks/`` (e.g. shell snippets); the generator skips those
    with a NOTICE rather than failing the build.
    """
    if not command:
        return None
    # Find the path token: last token ending in .py.
    tokens = command.split()
    py_tokens = [t for t in tokens if t.endswith(".py")]
    if not py_tokens:
        return None
    rel = py_tokens[-1].strip('"').strip("'")
    # Expected prefix .claude/hooks/. Strip and re-anchor under
    # ``script_source`` so this works regardless of whether the
    # command was authored relative to repo root or with an absolute
    # ``CLAUDE_PLUGIN_ROOT`` substitution.
    needle = ".claude/hooks/"
    if needle in rel:
        rel = rel.split(needle, 1)[1]
    candidate = script_source / rel
    if candidate.is_file():
        return candidate
    # Flat layout fallback: caller wrote ``.claude/hooks/foo.py`` but the
    # script lives at ``.claude/hooks/<Event>/foo.py``.
    nested = script_source / claude_event / rel
    if nested.is_file():
        return nested
    return None


def _matcher_suffix(matcher: str | None) -> str:
    """Derive a filesystem-safe, collision-free suffix from a matcher.

    A single source script registered under multiple matchers (e.g.
    ``invoke_session_log_guard.py`` against both ``Bash(git commit*)``
    and ``Bash(gh pr create*)``) must produce DIFFERENT shimmed copies
    on disk; otherwise the second copy clobbers the first and only one
    matcher fires.

    Naive sanitization (alnum -> ``_``) is NOT sufficient. Examples
    where two distinct matchers collapse to the same sanitized form:

    - ``Bash(../../etc/passwd)`` -> ``Bash_etc_passwd``
    - ``Bash(/etc/passwd)`` -> ``Bash_etc_passwd``
    - ``^(Edit|Write)$`` and ``^(Write|Edit)$`` differ in regex but
      sanitize identically

    To guarantee uniqueness we ALWAYS append a 6-character SHA-1 of the
    original matcher. The hash is deterministic (same input -> same
    suffix across runs), short enough to keep filenames readable, and
    guarantees no two distinct matchers produce the same target path.
    The cost (7 chars per filename) buys absolute determinism and
    closes the silent-clobber gate-bypass class of bug.
    """
    if not matcher:
        return ""
    # Sanitize: keep alnum + underscore; collapse runs; cap at 48 chars.
    sanitized = _re.sub(r"[^A-Za-z0-9]+", "_", matcher).strip("_")
    if len(sanitized) > 48:
        sanitized = sanitized[:48].rstrip("_")
    digest = hashlib.sha1(matcher.encode("utf-8"), usedforsecurity=False).hexdigest()[:6]
    if sanitized:
        return f"{sanitized}_{digest}"
    return digest


def _relative_script_target(
    target_root: Path,
    target_event: str,
    script_name: str,
    *,
    matcher: str | None = None,
) -> Path:
    if matcher:
        suffix = _matcher_suffix(matcher)
        if suffix and script_name.endswith(".py"):
            stem = script_name[: -len(".py")]
            return target_root / target_event / f"{stem}__{suffix}.py"
    return target_root / target_event / script_name


def _ensure_exact_case_dir(directory: Path) -> None:
    """Create ``directory`` ensuring its leaf name matches the exact case.

    On a case-insensitive filesystem (Windows, default macOS), a plain
    ``mkdir(exist_ok=True)`` silently reuses a pre-existing sibling whose name
    differs only by case. The directory then keeps its old casing in git while
    generated ``hooks.json`` paths use the new casing, producing a tree that
    works locally but fails on case-sensitive Linux (issue #2290). This walks
    the parent's real entries and renames any case-mismatched sibling to the
    intended case (two-step through a temp name to survive case-insensitive
    renames) before creating the directory.
    """
    parent = directory.parent
    parent.mkdir(parents=True, exist_ok=True)
    target_name = directory.name
    for entry in parent.iterdir():
        if entry.name == target_name:
            if not entry.is_dir():
                raise NotADirectoryError(
                    f"Target exists but is not a directory: {directory}"
                )
            return
        if entry.is_dir() and entry.name.lower() == target_name.lower():
            temp = parent / f"__case_fix_{target_name}"
            suffix = 1
            while temp.exists():
                temp = parent / f"__case_fix_{target_name}_{suffix}"
                suffix += 1
            entry.rename(temp)
            temp.rename(directory)
            return
        if entry.name.lower() == target_name.lower():
            raise NotADirectoryError(
                f"Case-conflicting path is not a directory: {entry}"
            )
    directory.mkdir(exist_ok=True)


def _copy_script(
    source: Path,
    target: Path,
    *,
    matcher: str | None,
    what_if: bool,
) -> tuple[bool, str]:
    """Copy a script to ``target``, optionally injecting a matcher shim.

    Honors NO-REGEN sentinel on the target. Returns ``(written, reason)``.
    ``written=False`` when a sentinel is detected; reason captures which
    sentinel. When ``matcher`` is non-empty the shim from
    :func:`inject_shim` is prepended; otherwise the script is copied
    verbatim.
    """
    reason = regen_detect_reason(target)
    if reason is not None:
        return False, f"NO-REGEN: {reason}"
    if what_if:
        return True, ""
    _ensure_exact_case_dir(target.parent)
    if not matcher:
        shutil.copyfile(source, target)
        return True, ""
    body = source.read_text(encoding="utf-8")
    transformed = inject_shim(body, matcher)
    target.write_text(transformed, encoding="utf-8")
    return True, ""


# --- Entry building -------------------------------------------------------


def _build_copilot_entry(
    target_event: str,
    script_name: str,
    *,
    timeout_sec: int = _DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Emit a single Copilot hook entry.

    The script path is anchored to the plugin install location via the
    ``COPILOT_PLUGIN_ROOT`` environment variable (Copilot CLI exposes a
    ``CLAUDE_PLUGIN_ROOT`` alias for Claude-plugin compatibility, used as
    a fallback). Copilot CLI runs hooks with ``cwd`` set to the user's
    working directory, NOT the plugin root, so a ``./hooks/...`` relative
    path resolves under the user's home/project and fails with
    "No such file or directory" (issue #2205). Anchoring at the plugin
    root makes the invocation work regardless of where the user launched
    ``copilot`` from.

    Both shells resolve the plugin root with the SAME fallback order
    (``COPILOT_PLUGIN_ROOT`` first, then ``CLAUDE_PLUGIN_ROOT``). The
    fallback was verified empirically against Copilot CLI 1.0.57: a
    plugin hook process is launched with BOTH variables set to the
    install directory (see the runtime-contract test in
    ``tests/build_scripts/test_generate_hooks_runtime_contract.py``).
    Keeping the two shells symmetric means a missing primary variable
    can never silently degrade one platform while the other recovers.

    The ``bash`` key invokes ``python3``; the ``powershell`` key invokes
    ``py -3``. RQ #4 in REQ-003 flags a Windows PATH risk for ``python3``;
    using ``py -3`` on Windows handles the case where only ``python.exe``
    is on PATH.
    POSIX ``bash`` uses parameter-expansion fallback
    (``${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}``). PowerShell has no
    ``${VAR:-default}`` form, so an ``if``/``else`` subexpression (valid
    in Windows PowerShell 5.1 and PowerShell 7+) provides the same
    fallback.
    """
    rel = f"hooks/{target_event}/{script_name}"
    bash_root = "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}"
    powershell_root = (
        "$(if ($env:COPILOT_PLUGIN_ROOT) "
        "{$env:COPILOT_PLUGIN_ROOT} else {$env:CLAUDE_PLUGIN_ROOT})"
    )
    return {
        "type": "command",
        "bash": f'python3 -u "{bash_root}/{rel}"',
        "powershell": f'py -3 -u "{powershell_root}/{rel}"',
        "cwd": ".",
        "timeoutSec": timeout_sec,
    }
