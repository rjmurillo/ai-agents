#!/usr/bin/env python3
"""Generate Copilot CLI hook config from ``.claude/settings.json`` (REQ-003-007).

Reads ``artifacts.hooks`` from a platform YAML, parses Claude's
``settings.json`` ``hooks`` object, copies each registered Python script
under ``.claude/hooks/`` into the Copilot output tree, and emits a
``hooks.json`` with the Copilot wire shape (``version: 1`` wrapper,
lowercase event names, no ``matcher`` field, ``cwd``-relative invocation).

This module ships the **core** in M5-T1. The matcher shim injector
(REQ-003-007 step 5) and idempotency (M5-T3) are added in subsequent
commits. Until then, scripts are copied verbatim and the Copilot config
omits matcher information; entries with a Claude-side ``matcher``
silently cover all tool calls.

EXIT CODES:
  0 - success
  1 - logic error (script not found, copy failure)
  2 - configuration error (missing stanza, malformed JSON, etc.)

Per ADR-035 Exit Code Standardization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from regen_guard import detect_reason as regen_detect_reason  # noqa: E402
from yaml_loader import (  # noqa: E402
    ConfigError,
    load_platform_config,
    validate_relative_path,
)

_DEFAULT_TIMEOUT_SEC = 30

# REQ-003-007 step 5: matcher shim sentinels. Idempotency check uses
# these exact tokens; do not reword without updating M5-T3 detection.
_SHIM_BEGIN = "# AUTO-GENERATED MATCHER SHIM (REQ-003-007)"
_SHIM_END = "# END MATCHER SHIM"

# Disambiguation classes for matcher patterns.
MATCHER_REGEX = "regex"
MATCHER_TOOL_GLOB = "tool-glob"
MATCHER_BARE = "bare"

# Pattern that recognizes the tool-glob shape `Tool(args*)`.
# Matches Bash(...), mcp__serena__write_memory(...), etc. Identifier rules
# match Python identifiers (REQ-003-007: ``[A-Za-z_][A-Za-z0-9_]*``).
import re as _re

_TOOL_GLOB_RE = _re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\((.*)\)$")


class GenerateHooksError(Exception):
    """Domain error for hook generation."""


# --- Matcher disambiguation -----------------------------------------------


def classify_matcher(pattern: str) -> tuple[str, dict[str, str]]:
    """Classify a matcher pattern per REQ-003-007 step 5.

    Returns ``(kind, params)`` where ``kind`` is one of MATCHER_REGEX,
    MATCHER_TOOL_GLOB, MATCHER_BARE and ``params`` carries the parsed
    pieces:

    - regex   -> {"pattern": <whole pattern>}
    - tool-glob -> {"toolName": <name>, "argsGlob": <inside parens>}
    - bare    -> {"toolName": <whole pattern>}

    The classification is explicit (not heuristic):

    1. Pattern starts with ``^`` AND ends with ``$`` -> regex.
    2. Pattern matches ``^[A-Za-z_]\\w*\\(.*\\)$`` -> tool-glob.
    3. Otherwise -> bare tool name.

    MIRROR: ``classify_matcher`` (build-time, this function) and
    ``_shim_classify`` (runtime, inlined into the shim template by
    :func:`_build_shim`) MUST agree on the grammar. Update both when
    the grammar changes; the live-corpus test only exercises the
    build-time version, so a runtime-only drift will not be caught.
    """
    if pattern.startswith("^") and pattern.endswith("$"):
        return MATCHER_REGEX, {"pattern": pattern}
    m = _TOOL_GLOB_RE.match(pattern)
    if m:
        return MATCHER_TOOL_GLOB, {
            "toolName": m.group(1),
            "argsGlob": m.group(2),
        }
    return MATCHER_BARE, {"toolName": pattern}


# --- Shim algorithm helpers (mirrored from shim body) --------------------
#
# These helpers exist at module scope so the test suite can target the
# whitespace-normalization and glob-OR-fold algorithms directly without
# spawning a subprocess. The shim body emits the same algorithm inline
# so generated scripts have zero import dependency on this module.


def normalize_tool_args(tool_args: object) -> str:
    r"""Stringify and collapse \s+ to a single space; strip ends.

    REQ-003-007 step 5: applied to ``toolArgs`` at runtime, NOT to the
    pattern. ``dict`` toolArgs that carry a ``command`` field (e.g.
    ``{"command": "git commit -m foo"}`` from Bash) are reduced to that
    string; other dicts are stringified via ``json.dumps`` for stable
    comparison.
    """
    if isinstance(tool_args, dict):
        cmd = tool_args.get("command")
        if isinstance(cmd, str):
            text = cmd
        else:
            text = json.dumps(tool_args, sort_keys=True)
    elif isinstance(tool_args, str):
        text = tool_args
    elif tool_args is None:
        text = ""
    else:
        text = str(tool_args)
    return _re.sub(r"\s+", " ", text).strip()


def glob_or_match(args_glob: str, tool_args_norm: str) -> bool:
    """OR-fold an argsGlob with ``|`` alternation against tool_args_norm.

    REQ-003-007 step 5: ``fnmatch`` treats ``|`` as a literal; authors
    expect Claude semantics where each branch is a separate glob.
    """
    import fnmatch as _fn
    branches = args_glob.split("|") if args_glob else [""]
    for branch in branches:
        if _fn.fnmatchcase(tool_args_norm, branch):
            return True
    return False


# --- Shim source generation ----------------------------------------------


def _build_shim(matcher: str) -> str:
    """Return the Python source code for the matcher shim.

    The shim:

    - buffers stdin once into ``_raw`` (bytes), guaranteeing the original
      script's ``sys.stdin.read()`` sees the same bytes the matcher
      inspected;
    - dispatches by classified matcher kind;
    - exits 0 silently when the matcher does not fire (no-op = allow);
    - exits 2 to stderr on any internal error (regex parse, JSON decode,
      missing toolName) so Copilot CLI surfaces the failure rather than
      silently allowing the tool call;
    - calls the wrapped ``_original_main(_raw)`` only on a positive
      match, propagating its exit code.

    The original script body is wrapped into ``_original_main`` by
    :func:`inject_shim`.
    """
    # The shim is emitted as a single triple-quoted block so the indenting
    # is stable. We do NOT f-string the matcher into the shim body; we
    # bind it via repr() inside a Python literal so embedded quotes are
    # safe.
    return f'''\
{_SHIM_BEGIN}
# Matcher: {matcher}
# Generated by build/scripts/generate_hooks.py (REQ-003-007).
# DO NOT EDIT BY HAND - regenerated on every build. Apply NO-REGEN
# sentinel ("# NO-REGEN" or sidecar .noregen) to opt out.
import os as _os
import sys as _sys
import io as _io
import json as _json
import re as _re
import fnmatch as _fnmatch

_MATCHER = {matcher!r}


def _shim_classify(pattern):
    # MIRROR: classify_matcher (build-time, build/scripts/generate_hooks.py)
    # and _shim_classify (runtime, this inlined copy) MUST agree on the
    # grammar. Update both when the grammar changes.
    if pattern.startswith("^") and pattern.endswith("$"):
        return "regex", {{"pattern": pattern}}
    m = _re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\\((.*)\\)$", pattern)
    if m:
        return "tool-glob", {{"toolName": m.group(1), "argsGlob": m.group(2)}}
    return "bare", {{"toolName": pattern}}


def _shim_normalize_args(tool_args):
    r"""Stringify and whitespace-normalize toolArgs for fnmatch comparison.

    REQ-003-007: collapse \\s+ to a single space and strip ends. Pattern
    is NOT normalized; authors write patterns assuming single spaces.
    """
    if isinstance(tool_args, dict):
        # Bash hooks place command under "command"; keep this fallback
        # path narrow but correct for the live corpus.
        cmd = tool_args.get("command")
        if isinstance(cmd, str):
            text = cmd
        else:
            text = _json.dumps(tool_args, sort_keys=True)
    elif isinstance(tool_args, str):
        text = tool_args
    elif tool_args is None:
        text = ""
    else:
        text = str(tool_args)
    return _re.sub(r"\\s+", " ", text).strip()


def _shim_glob_match(args_glob, tool_args_norm):
    """Match args_glob against tool_args_norm with `|` as alternation.

    fnmatch treats `|` as a literal. Authors expect Claude semantics
    where each `|` branch is a separate glob alternation. Split on
    top-level `|` and OR-fold the results.
    """
    branches = args_glob.split("|") if args_glob else [""]
    for branch in branches:
        if _fnmatch.fnmatchcase(tool_args_norm, branch):
            return True
    return False


def _shim_should_fire(payload):
    kind, params = _shim_classify(_MATCHER)
    tool_name = payload.get("toolName")
    if not isinstance(tool_name, str):
        raise ValueError("hook input missing string `toolName` field")
    if kind == "regex":
        return _re.fullmatch(params["pattern"], tool_name) is not None
    if kind == "tool-glob":
        if tool_name != params["toolName"]:
            return False
        norm_args = _shim_normalize_args(payload.get("toolArgs"))
        return _shim_glob_match(params["argsGlob"], norm_args)
    # bare
    return tool_name == params["toolName"]


def _shim_dispatch():
    try:
        _raw = _sys.stdin.buffer.read()
    except Exception as exc:  # pragma: no cover - defensive
        print(
            "matcher-shim [{{}}]: failed to buffer stdin: {{}}".format(_MATCHER, exc),
            file=_sys.stderr,
        )
        _sys.exit(2)
    try:
        payload = _json.loads(_raw or b"{{}}")
    except _json.JSONDecodeError as exc:
        print(
            "matcher-shim [{{}}]: malformed JSON on stdin: {{}}".format(_MATCHER, exc),
            file=_sys.stderr,
        )
        _sys.exit(2)
    try:
        fire = _shim_should_fire(payload)
    except Exception as exc:
        print(
            "matcher-shim [{{}}]: dispatch error: {{}}".format(_MATCHER, exc),
            file=_sys.stderr,
        )
        _sys.exit(2)
    if _os.environ.get("COPILOT_HOOK_DEBUG"):
        kind, _ = _shim_classify(_MATCHER)
        _sys.stderr.write(
            "matcher-shim [{{}}]: kind={{}} fired={{}}\\n".format(_MATCHER, kind, fire)
        )
    if not fire:
        _sys.exit(0)
    # Replay raw bytes into a fresh stdin so the original script reads
    # exactly what the shim inspected. Replace BEFORE calling original.
    _sys.stdin = _io.TextIOWrapper(_io.BytesIO(_raw), encoding="utf-8")
    rc = _original_main(_raw)
    if rc is None:
        rc = 0
    _sys.exit(int(rc))


{_SHIM_END}
'''


def _wrap_body_in_function(body: str) -> str:
    """Indent ``body`` and wrap it in ``def _original_main(stdin_bytes):``.

    The original script's top-level statements become the function body.
    A trailing ``return 0`` makes scripts that exit by falling off the
    bottom return a clean exit code. Scripts that call ``sys.exit(...)``
    explicitly are unaffected: ``SystemExit`` propagates through the
    function call.

    The wrapper preserves the original script's line numbers for
    debugging by emitting a leading ``# original script begins`` marker.
    """
    indented = "\n".join("    " + line if line else "" for line in body.splitlines())
    return (
        "def _original_main(stdin_bytes):\n"
        + "    # original script body begins below\n"
        + indented
        + "\n    return 0\n"
    )


def is_shimmed(source: str) -> bool:
    """Return True when ``source`` already carries the matcher shim.

    Detection is the literal :data:`_SHIM_BEGIN` sentinel. Subsequent
    generator runs use this to drive idempotent replacement.
    """
    return _SHIM_BEGIN in source


def inject_shim(original: str, matcher: str) -> str:
    """Return original script source with the matcher shim prepended.

    Idempotent (M5-T3): if the original already carries the shim
    sentinels, the existing shim block is stripped and replaced rather
    than stacked. A second :func:`inject_shim` call yields the same
    output as a first call against the never-shimmed body, preserving
    the invariant that the file contains exactly ONE shim block.
    """
    stripped = strip_shim(original) if is_shimmed(original) else original
    shim = _build_shim(matcher)
    wrapped = _wrap_body_in_function(stripped)
    return shim + "\n" + wrapped + "\n_shim_dispatch()\n"


def _find_shim_bounds(lines: list[str]) -> tuple[int, int] | None:
    """Locate the ``(begin, end)`` line indices of a shim block.

    Returns ``None`` when either sentinel is missing. Indices are inclusive
    on both ends so the caller can slice ``lines[end+1:]`` to skip past
    the shim header.
    """
    begin_idx: int | None = None
    for i, line in enumerate(lines):
        if line.rstrip("\n") == _SHIM_BEGIN:
            begin_idx = i
            break
    if begin_idx is None:
        return None
    for i in range(begin_idx + 1, len(lines)):
        if lines[i].rstrip("\n") == _SHIM_END:
            return begin_idx, i
    return None


def _extract_original_body(after_shim: list[str]) -> str:
    """Reconstruct the original script body from post-shim lines.

    Expects the layout :func:`inject_shim` writes:
    optional blank lines, ``def _original_main(stdin_bytes):``, an
    optional ``# original script body begins below`` marker, the
    indented body, a synthetic trailing ``return 0``, and the final
    ``_shim_dispatch()`` invocation. Anything past the dispatch call is
    returned verbatim as the tail.

    When no wrapper is detected (shim block was present but the
    function wrapper is not), the lines are returned as-is so callers
    fall back to a strip-only behavior.
    """
    j = 0
    while j < len(after_shim) and not after_shim[j].strip():
        j += 1
    if j >= len(after_shim) or not after_shim[j].startswith("def _original_main("):
        # No wrapper: caller will fall back to plain strip.
        return "".join(after_shim[j:])

    # Drop the def line and any leading body marker.
    j += 1
    if j < len(after_shim) and after_shim[j].lstrip().startswith(
        "# original script body begins below"
    ):
        j += 1

    body_lines: list[str] = []
    while j < len(after_shim):
        line = after_shim[j]
        if not line.strip():
            body_lines.append("\n")
            j += 1
            continue
        if line.startswith("    "):
            body_lines.append(line[4:])
            j += 1
            continue
        break  # Non-indented line ends the function body.

    # Trim the synthetic trailing ``return 0`` we appended.
    while body_lines and body_lines[-1].strip() == "":
        body_lines.pop()
    if body_lines and body_lines[-1].rstrip() == "return 0":
        body_lines.pop()
        while body_lines and body_lines[-1].strip() == "":
            body_lines.pop()

    # Skip a single trailing ``_shim_dispatch()`` invocation if present.
    while j < len(after_shim) and not after_shim[j].strip():
        j += 1
    if j < len(after_shim) and after_shim[j].strip() == "_shim_dispatch()":
        j += 1

    body_text = "".join(body_lines)
    tail = "".join(after_shim[j:])
    if body_text and not body_text.endswith("\n"):
        body_text += "\n"
    return body_text + tail


def strip_shim(source: str) -> str:
    """Remove a previously-injected shim block. M5-T3 idempotency.

    Detection is by exact sentinel string match (see :func:`_find_shim_bounds`).
    The shim header, the ``def _original_main`` wrapper, and the trailing
    ``_shim_dispatch()`` call are all removed; the original script body
    is restored from the wrapper's indented lines.
    """
    if _SHIM_BEGIN not in source:
        return source
    lines = source.splitlines(keepends=True)
    bounds = _find_shim_bounds(lines)
    if bounds is None:
        return source
    begin_idx, end_idx = bounds
    head = "".join(lines[:begin_idx])
    body = _extract_original_body(lines[end_idx + 1 :])
    return head + body


@dataclass
class HookAuditEntry:
    """One hook script's outcome — used by tests and audit."""

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
    digest = hashlib.sha1(matcher.encode("utf-8")).hexdigest()[:6]  # noqa: S324
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
    target.parent.mkdir(parents=True, exist_ok=True)
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

    The ``bash`` and ``powershell`` keys both invoke ``python3``. RQ #4
    in REQ-003 flags a Windows PATH risk for ``python3``; using ``py -3``
    on Windows handles the case where only ``python.exe`` is on PATH.
    """
    rel = f"./hooks/{target_event}/{script_name}"
    return {
        "type": "command",
        "bash": f'python3 -u "{rel}"',
        "powershell": f'py -3 -u "{rel}"',
        "cwd": ".",
        "timeoutSec": timeout_sec,
    }


# --- Driver ---------------------------------------------------------------


def _iter_hooks(groups: list[Any]) -> "Iterable[tuple[dict[str, Any], dict[str, Any]]]":
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
    timeout = int(hook.get("timeout", _DEFAULT_TIMEOUT_SEC) or _DEFAULT_TIMEOUT_SEC)
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
    version_field = int(stanza.get("versionField", 1) or 1)

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
        for target_event, entry in emitted:
            out.setdefault(target_event, []).append(entry)

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


# --- CLI ------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Platform YAML config (defaults to templates/platforms/copilot-cli.yaml).",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (defaults to script's grandparent).",
    )
    p.add_argument("--what-if", action="store_true", help="Dry-run mode.")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root or _SCRIPT_DIR.parent.parent
    config_path = args.config or (
        repo_root / "templates" / "platforms" / "copilot-cli.yaml"
    )
    if not config_path.is_file():
        print(f"Error: config not found: {config_path}", file=sys.stderr)
        return 2
    rc, _result = generate_hooks(config_path, repo_root, what_if=args.what_if)
    return rc


if __name__ == "__main__":
    sys.exit(main())
