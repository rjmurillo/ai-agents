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
allow), with the first non-zero wrapped result when candidates match,
or 0 when all matching candidates allow. It exits 2 to stderr on any
internal error: missing ``tool_name`` field,
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

# Policy source of truth for dispatchers and emitted standalone matcher shims.
HOOK_STDIN_CEILING_MIB = 64
MATCHED_SHIM_PAYLOAD_LIMIT_MIB = 2
# Bound per-event candidate copies and guard executions after the raw-byte cap.
MAX_MATCHER_TOOL_CALLS = 256

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
    - calls the wrapped ``_original_main`` for each matching candidate in
      order, stopping at the first non-zero result.

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

# Bound the standalone shim read before JSON parsing so a malicious or buggy
# upstream cannot cause unbounded allocation (CWE-400).
_HOOK_STDIN_CEILING_BYTES = {HOOK_STDIN_CEILING_MIB} * 1024 * 1024

# Apply the normal payload policy only after matcher selection. Multi-call
# events can contain a large unrelated call that must not deny a small matched
# call.
_MATCHED_SHIM_PAYLOAD_LIMIT_BYTES = {MATCHED_SHIM_PAYLOAD_LIMIT_MIB} * 1024 * 1024
_MAX_MATCHER_TOOL_CALLS = {MAX_MATCHER_TOOL_CALLS}


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


def _shim_parse_json_string(raw_value, field_name):
    if isinstance(raw_value, str):
        stripped = raw_value.lstrip()
        if not stripped or stripped[0] not in "{{[\\"":
            return raw_value
        try:
            return _json.loads(raw_value)
        except ValueError as exc:
            print(
                "matcher-shim [{{}}]: {{}} is not valid JSON: {{}}".format(
                    _MATCHER, field_name, exc
                ),
                file=_sys.stderr,
            )
            return raw_value
    return raw_value


def _shim_tool_input_from_call_args(raw_args):
    return _shim_parse_json_string(raw_args, "toolCalls.args")


def _shim_tool_input_from_tool_args(raw_args):
    return _shim_parse_json_string(raw_args, "toolArgs")


def _shim_top_level_input_field(payload):
    if payload.get("tool_input") is not None:
        return "tool_input"
    if "toolArgs" in payload:
        return "toolArgs"
    return "tool_input"


def _shim_validate_tool_name(name, field):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("{{}} must be a non-empty string".format(field))
    if name != name.strip():
        raise ValueError(
            "{{}} must not have leading or trailing whitespace".format(field)
        )
    return name


def _shim_top_level_candidate(payload):
    name_fields = [key for key in ("tool_name", "toolName") if key in payload]
    if not name_fields:
        raise ValueError("hook input missing string `tool_name`/`toolName` field")
    names = [
        _shim_validate_tool_name(payload[field], field)
        for field in name_fields
    ]
    if len(names) == 2 and names[0] != names[1]:
        raise ValueError("conflicting top-level tool_name/toolName values")
    return payload, _shim_top_level_input_field(payload)


def _shim_candidate_payloads(payload):
    if "toolCalls" in payload:
        tool_calls = payload["toolCalls"]
        if not isinstance(tool_calls, list):
            raise ValueError("toolCalls must be a list when present")
        if len(tool_calls) > _MAX_MATCHER_TOOL_CALLS:
            raise ValueError(
                "toolCalls contains {{}} entries; limit is {{}}".format(
                    len(tool_calls), _MAX_MATCHER_TOOL_CALLS
                )
            )
        if not tool_calls and (
            "tool_name" in payload or "toolName" in payload
        ):
            raise ValueError(
                "empty toolCalls conflicts with top-level tool_name/toolName"
            )
        for index, call in enumerate(tool_calls):
            if not isinstance(call, dict):
                raise ValueError(
                    "toolCalls[{{}}] must be an object".format(index)
                )
            _shim_validate_tool_name(
                call.get("name"), "toolCalls[{{}}].name".format(index)
            )
        for call in tool_calls:
            name = call["name"]
            candidate = dict(payload)
            for field in (
                "toolCalls",
                "tool_name",
                "toolName",
                "tool_input",
                "toolArgs",
                "tool_call_id",
                "toolCallId",
            ):
                candidate.pop(field, None)
            candidate["tool_name"] = name
            candidate["tool_input"] = _shim_tool_input_from_call_args(call.get("args"))
            if "id" in call:
                candidate["tool_call_id"] = call.get("id")
            yield candidate, "toolCalls.args"
        return
    yield _shim_top_level_candidate(payload)


def _shim_match_candidate(payload, kind, params):
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
        tool_args = _shim_tool_input_from_tool_args(tool_args)
        norm_args = _shim_normalize_args(tool_args)
        return _shim_glob_match(params["argsGlob"], norm_args)
    # bare
    return tool_name == params["toolName"]


def _shim_select_payloads(payload):
    kind, params = _shim_classify(_MATCHER)
    for candidate, input_field in _shim_candidate_payloads(payload):
        if _shim_match_candidate(candidate, kind, params):
            yield candidate, input_field


def _shim_replay_bytes(payload, selected, raw):
    replay = dict(selected)
    changed = selected is not payload
    tool_name = replay.get("tool_name")
    if tool_name is None and isinstance(replay.get("toolName"), str):
        replay["tool_name"] = replay["toolName"]
        changed = True
    tool_input = replay.get("tool_input")
    if tool_input is None and "toolArgs" in replay:
        replay["tool_input"] = _shim_tool_input_from_tool_args(replay.get("toolArgs"))
        changed = True
    if not changed:
        return raw
    return _json.dumps(replay, separators=(",", ":")).encode("utf-8")


def _shim_exit_code(exc):
    code = exc.code
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    return 1


def _shim_invoke_selection(payload, selection, raw):
    selected, input_field = selection
    replay = _shim_replay_bytes(payload, selected, raw)
    if len(replay) > _MATCHED_SHIM_PAYLOAD_LIMIT_BYTES:
        print(
            (
                "matcher-shim [{{}}]: matched replay from {{}} exceeds "
                "{{}} bytes; refusing"
            ).format(_MATCHER, input_field, _MATCHED_SHIM_PAYLOAD_LIMIT_BYTES),
            file=_sys.stderr,
        )
        return 2
    _sys.stdin = _io.TextIOWrapper(_io.BytesIO(replay), encoding="utf-8")
    try:
        rc = _original_main(replay)
    except SystemExit as exc:
        return _shim_exit_code(exc)
    if rc is None:
        return 0
    return int(rc)


def _shim_dispatch_selections(payload):
    try:
        yield from _shim_select_payloads(payload)
    except Exception as exc:
        print(
            "matcher-shim [{{}}]: dispatch error: {{}}".format(_MATCHER, exc),
            file=_sys.stderr,
        )
        _sys.exit(2)


def _shim_debug_trace(fire):
    if not _os.environ.get("COPILOT_HOOK_DEBUG"):
        return
    kind, _ = _shim_classify(_MATCHER)
    _sys.stderr.write(
        "matcher-shim [{{}}]: kind={{}} fired={{}}\\n".format(_MATCHER, kind, fire)
    )


def _shim_dispatch():
    try:
        _raw = _sys.stdin.buffer.read(_HOOK_STDIN_CEILING_BYTES + 1)
    except Exception as exc:  # pragma: no cover - defensive
        print(
            "matcher-shim [{{}}]: failed to buffer stdin: {{}}".format(_MATCHER, exc),
            file=_sys.stderr,
        )
        _sys.exit(2)
    if len(_raw) > _HOOK_STDIN_CEILING_BYTES:
        print(
            "matcher-shim [{{}}]: stdin exceeds {{}} bytes; refusing".format(
                _MATCHER, _HOOK_STDIN_CEILING_BYTES
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
    fire = False
    for selection in _shim_dispatch_selections(payload):
        if not fire:
            fire = True
            _shim_debug_trace(fire)
        rc = _shim_invoke_selection(payload, selection, _raw)
        if rc != 0:
            _sys.exit(rc)
    if not fire:
        _shim_debug_trace(fire)
    _sys.exit(0)
{_SHIM_END}
'''
