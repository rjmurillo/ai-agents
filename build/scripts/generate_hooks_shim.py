#!/usr/bin/env python3
"""Matcher classification and shim-source generation for Copilot CLI hooks.

Extracted from ``generate_hooks.py`` (issue #2223) so the generator stays
under the file-size taste limit. This module owns two cohesive concerns:

1. Build-time matcher classification (:func:`classify_matcher`,
   :func:`normalize_tool_args`, :func:`glob_or_match`). These mirror the
   algorithm the shim emits inline so tests can target them directly without
   spawning a subprocess.
2. Shim source generation (:func:`_build_shim` plus the ``_SHIM_BEGIN`` /
   ``_SHIM_END`` sentinels). The shim wraps a Claude hook script so it only
   fires when its matcher matches the live tool call.

MATCHER GRAMMAR
---------------

Three classes are supported (see :func:`classify_matcher`):

- ``regex``: pattern starts with ``^`` AND ends with ``$``.
  Example: ``^(Edit|Write)$`` (anchored full-tool-name match).
- ``tool-glob``: pattern matches ``^[A-Za-z_][A-Za-z0-9_]*\\((.*)\\)$``.
  Example: ``Bash(git commit*|gh pr create*)`` (toolName then
  fnmatch on the args). ``|`` inside the parens is OR-folded across
  branches; whitespace in tool args is collapsed before matching.
- ``bare``: anything else; treated as a literal tool name.
  Example: ``mcp__serena__write_memory``.

Adding a new matcher kind requires updating BOTH classifiers
(:func:`classify_matcher` build-time and ``_shim_classify`` runtime,
inlined into the shim template by :func:`_build_shim`) plus the
parametrized tests in ``tests/build_scripts/test_generate_hooks.py``.

SHIM CRASH POLICY
-----------------

The shim exits with code 0 when the matcher does not fire (no-op
allow), 0 with the wrapped script's exit code when it does fire, and
2 to stderr on any internal error: missing ``tool_name`` field,
malformed JSON on stdin, regex parse failure. NEVER 0 silently on a
malformed input; that would silently allow tool calls past a
broken hook.
"""

from __future__ import annotations

import json
import re as _re

# Disambiguation classes for matcher patterns.
MATCHER_REGEX = "regex"
MATCHER_TOOL_GLOB = "tool-glob"
MATCHER_BARE = "bare"

# Pattern that recognizes the tool-glob shape `Tool(args*)`.
# Matches Bash(...), mcp__serena__write_memory(...), etc. Identifier rules
# match Python identifiers (REQ-003-007: ``[A-Za-z_][A-Za-z0-9_]*``).
_TOOL_GLOB_RE = _re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\((.*)\)$")

# REQ-003-007 step 5: matcher shim sentinels. Idempotency check uses
# these exact tokens; do not reword without updating M5-T3 detection.
_SHIM_BEGIN = "# AUTO-GENERATED MATCHER SHIM (REQ-003-007)"
_SHIM_END = "# END MATCHER SHIM"


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
    2. Pattern matches ``^[A-Za-z_][A-Za-z0-9_]*\\(.*\\)$`` -> tool-glob.
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

    REQ-003-007 step 5: applied to ``tool_input`` at runtime, NOT to the
    pattern. ``dict`` tool_input that carry a ``command`` field (e.g.
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

    - buffers stdin once into ``_raw`` (bytes), preserving those bytes for
      already snake_case payloads and canonicalizing camelCase payloads before
      replay so wrapped hooks read the schema they enforce;
    - dispatches by classified matcher kind;
    - exits 0 silently when the matcher does not fire (no-op = allow);
    - exits 2 to stderr on any internal error (regex parse, JSON decode,
      missing tool_name) so Copilot CLI surfaces the failure rather than
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

# Cap stdin read so a malicious or buggy upstream cannot OOM the shim
# (CWE-400). Mirrors push_guard_base.MAX_STDIN_BYTES (1 MiB) with a
# small headroom; real Claude/Copilot tool_input commands are well
# below this limit. The cap belongs at the SHIM layer because the
# shim reads stdin BEFORE delegating to the wrapped script. Without
# it, the wrapped script's own cap is applied too late: the OOM has
# already happened.
_SHIM_MAX_STDIN_BYTES = 2 * 1024 * 1024


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
    r"""Stringify and whitespace-normalize tool_input for fnmatch comparison.

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
    # Support both VS Code-compatible snake_case (PascalCase event names)
    # and native camelCase (camelCase event names) payloads.
    # Copilot CLI sends snake_case when the event key is PascalCase,
    # camelCase when the event key is camelCase. See issue #2290.
    tool_name = payload.get("tool_name")
    if tool_name is None:
        tool_name = payload.get("toolName")
    if not isinstance(tool_name, str):
        raise ValueError("hook input missing string `tool_name`/`toolName` field")
    if kind == "regex":
        return _re.fullmatch(params["pattern"], tool_name) is not None
    if kind == "tool-glob":
        if tool_name != params["toolName"]:
            return False
        tool_args = payload.get("tool_input")
        if tool_args is None:
            tool_args = payload.get("toolArgs")
        # camelCase payloads send toolArgs as a JSON string, not a parsed
        # object. Parse it so _shim_normalize_args can extract "command".
        if isinstance(tool_args, str):
            try:
                tool_args = _json.loads(tool_args)
            except ValueError as exc:
                # Host sent a string that is not valid JSON. Log so
                # the operator can diagnose; fall through to normalize
                # which treats raw strings as-is (glob may not match).
                print(
                    "matcher-shim [{{}}]: toolArgs is not valid JSON: {{}}".format(
                        _MATCHER, exc
                    ),
                    file=_sys.stderr,
                )
        norm_args = _shim_normalize_args(tool_args)
        return _shim_glob_match(params["argsGlob"], norm_args)
    # bare
    return tool_name == params["toolName"]


def _shim_replay_bytes(payload, raw):
    replay = dict(payload)
    changed = False
    tool_name = replay.get("tool_name")
    if tool_name is None and isinstance(replay.get("toolName"), str):
        replay["tool_name"] = replay["toolName"]
        changed = True
    tool_input = replay.get("tool_input")
    if tool_input is None and "toolArgs" in replay:
        tool_args = replay.get("toolArgs")
        if isinstance(tool_args, str):
            try:
                tool_args = _json.loads(tool_args)
            except ValueError:
                pass
        replay["tool_input"] = tool_args
        changed = True
    if not changed:
        return raw
    return _json.dumps(replay, separators=(",", ":")).encode("utf-8")


def _shim_dispatch():
    try:
        _raw = _sys.stdin.buffer.read(_SHIM_MAX_STDIN_BYTES + 1)
    except Exception as exc:  # pragma: no cover - defensive
        print(
            "matcher-shim [{{}}]: failed to buffer stdin: {{}}".format(_MATCHER, exc),
            file=_sys.stderr,
        )
        _sys.exit(2)
    if len(_raw) > _SHIM_MAX_STDIN_BYTES:
        print(
            "matcher-shim [{{}}]: stdin exceeds {{}} bytes; refusing".format(
                _MATCHER, _SHIM_MAX_STDIN_BYTES
            ),
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
    # Replay a canonical payload into a fresh stdin so wrapped hooks enforce
    # the same schema even when the host sent the camelCase variant.
    _replay = _shim_replay_bytes(payload, _raw)
    _sys.stdin = _io.TextIOWrapper(_io.BytesIO(_replay), encoding="utf-8")
    rc = _original_main(_replay)
    if rc is None:
        rc = 0
    _sys.exit(int(rc))


{_SHIM_END}
'''
