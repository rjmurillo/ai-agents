"""Emit Copilot CLI dispatcher artifacts (ADR-068, #2295, #2342).

Wired via ``generate_hooks_events.py`` when ``artifacts.hooks.dispatcher`` is
true (only the Copilot CLI platform sets it). Each safely mergeable event is
consolidated to one in-process dispatcher entry, so Copilot spawns at most one
interpreter per event trigger instead of one per registered shim (#2342).

Each consolidated event runs in one of three modes:

- ``gate`` (``PreToolUse``): the dispatcher short-circuits on the first non-zero
  shim exit and returns that exit code.
- ``observe`` (``PostToolUse``, ``PreCompact``, ``SessionStart``,
  ``UserPromptSubmit``): the dispatcher runs every shim regardless of an
  earlier non-zero shim exit and returns 0 for shim outcomes and oversize input,
  matching the pre-consolidation host behavior where the host ran every observer
  entry. Entrypoint faults still return 2 after a fixed diagnostic; the host
  decides whether an observer failure blocks or continues.
- ``advise`` (``PermissionRequest``): exactly one canonical Claude decision
  producer runs. Its stdout is translated to Copilot's permission response.

``Stop`` and ``SubagentStop`` stay as direct host registrations. Those events
can return structured decisions from more than one hook. Concatenating those
objects inside an observe dispatcher produces malformed JSON, while Copilot
already knows how to merge separate hook results.
Any event outside the explicit mode allowlists also stays direct. A future
event's stdout and exit semantics must be reviewed before consolidation.

For an event whose registered matcher shims are ``shim_names`` (in hooks.json
order, the authoritative registered set, NOT a directory listing), it produces:

- ``_manifest.json`` next to the shims: the ordered shim list plus the event's
  ``mode``; the dispatcher runs the shims in-process.
- ``_dispatch.py`` next to the shims: the thin entrypoint the host invokes once
  per event; it reads stdin and the manifest mode, then delegates to
  ``hook_dispatch.run_dispatch`` with the matching ``short_circuit`` flag.
  The entrypoint validates per-shim timeout metadata, but the host owns the
  cumulative event timeout. In-process timeout threads are intentionally not
  used because Python cannot kill them safely.
- ``_bootstrap.py`` next to the shims (copied from the canonical
  ``.claude/hooks/PreToolUse/_bootstrap.py``): the entrypoint imports
  ``ensure_plugin_paths`` from it, so every consolidated event dir needs a copy.
- the single ``hooks.json`` entry (via :func:`dispatcher_entry`) that points the
  host at ``_dispatch.py`` for that event.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import stat
from pathlib import Path
from typing import Any

from generate_hooks_body import is_shimmed
from generate_hooks_shim import HOOK_STDIN_CEILING_MIB
from regen_guard import detect_reason_strict as regen_detect_reason

# Mirror contract from build/scripts/generate_hooks_emit.py::_build_copilot_entry:
# bash_root = "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}"
# powershell_root = (
#     "$(if ($env:COPILOT_PLUGIN_ROOT) "
#     "{$env:COPILOT_PLUGIN_ROOT} else {$env:CLAUDE_PLUGIN_ROOT})"
# )
# "bash": f'python3 -u "{bash_root}/{rel}"'
# "powershell": f'py -3 -u "{powershell_root}/{rel}"'
# "cwd": "."
# "timeoutSec": timeout_sec
# The dispatcher swaps {rel} to point at the per-event _dispatch.py but keeps
# root resolution and shell shape identical.
# Minimum Python version required by the hook runtime. Oldest version still
# receiving security patches as of 2026. The hook code uses f-strings (3.6+)
# and `from __future__ import annotations` (3.7+), but we declare 3.10 as the
# supported floor to match the Python lifecycle.
_MIN_PYTHON_MAJOR = 3
_MIN_PYTHON_MINOR = 10

_WARN_PREFIX = "project-toolkit@ai-agents WARNING: hooks DISABLED (your session is unaffected)."

_BASH_TEMPLATE = (
    '_ptr="${{COPILOT_PLUGIN_ROOT:-${{CLAUDE_PLUGIN_ROOT}}}}"; '
    '_warn="project-toolkit@ai-agents WARNING: hooks DISABLED '
    '(your session is unaffected)."; '
    'if [ -z "$_ptr" ]; then '
    'echo "$_warn Plugin root unresolvable (COPILOT_PLUGIN_ROOT and '
    'CLAUDE_PLUGIN_ROOT both empty). '
    'Reinstall: copilot plugin install project-toolkit@ai-agents" >&2; '
    'exit 0; fi; '
    'if [ ! -d "$_ptr" ]; then '
    'echo "$_warn Plugin root is not a directory: $_ptr. '
    'Reinstall: copilot plugin install project-toolkit@ai-agents" >&2; '
    'exit 0; fi; '
    # Interpreter discovery: preflight each candidate with a version check.
    # A broken launcher (exits nonzero) or too-old interpreter (< 3.10) moves
    # to the next candidate. Covers HIGH 3 and HIGH 5 from #4672 review.
    '_interp=""; '
    'for _c in python3 python; do '
    'if command -v "$_c" >/dev/null 2>&1; then '
    '_ok=$("$_c" -I -c "import sys;'
    'print(int(sys.version_info>=({min_maj},{min_min})))" 2>/dev/null) || _ok=""; '
    'if [ "$_ok" = "1" ]; then _interp="$_c"; break; fi; '
    'fi; done; '
    'if [ -z "$_interp" ]; then '
    'echo "$_warn No suitable Python interpreter found (need >= {min_maj}.{min_min}). '
    'Install: https://www.python.org/downloads/" >&2; exit 0; fi; '
    # Dispatcher must be a regular file and readable (not a directory).
    'if [ ! -f "$_ptr/hooks/{event}/_dispatch.py" ]; then '
    'echo "$_warn Dispatcher missing or not a file: '
    '$_ptr/hooks/{event}/_dispatch.py. '
    'Reinstall: copilot plugin install project-toolkit@ai-agents" >&2; '
    'exit 0; fi; '
    'if [ ! -r "$_ptr/hooks/{event}/_dispatch.py" ]; then '
    'echo "$_warn Dispatcher unreadable: '
    '$_ptr/hooks/{event}/_dispatch.py. '
    'Reinstall: copilot plugin install project-toolkit@ai-agents" >&2; '
    'exit 0; fi; '
    '"$_interp" -I -u "$_ptr/hooks/{event}/_dispatch.py"; _rc=$?; '
    'if [ $_rc -eq 126 ] || [ $_rc -eq 127 ]; then '
    'echo "$_warn Python interpreter failed to start ($_interp, exit $_rc). '
    'Install Python >= {min_maj}.{min_min}: '
    'https://www.python.org/downloads/" >&2; exit 0; fi; '
    'exit $_rc'
)
_PWSH_TEMPLATE = (
    '$_ptr = if ($env:COPILOT_PLUGIN_ROOT) {{ $env:COPILOT_PLUGIN_ROOT }} '
    'elseif ($env:CLAUDE_PLUGIN_ROOT) {{ $env:CLAUDE_PLUGIN_ROOT }} '
    'else {{ $null }}; '
    '$_warn = "project-toolkit@ai-agents WARNING: hooks DISABLED '
    '(your session is unaffected)."; '
    'if (-not $_ptr) {{ '
    '[Console]::Error.WriteLine("$_warn Plugin root unresolvable '
    '(COPILOT_PLUGIN_ROOT and CLAUDE_PLUGIN_ROOT both empty). '
    'Reinstall: copilot plugin install project-toolkit@ai-agents"); exit 0 }}; '
    'if (-not (Test-Path $_ptr -PathType Container)) {{ '
    '[Console]::Error.WriteLine("$_warn Plugin root is not a directory: $_ptr. '
    'Reinstall: copilot plugin install project-toolkit@ai-agents"); exit 0 }}; '
    # Interpreter discovery: preflight each candidate with version check.
    # A broken launcher or too-old interpreter moves to the next candidate.
    '$_interp = $null; '
    'foreach ($c in @("py","python3","python")) {{ '
    'if (Get-Command $c -ErrorAction SilentlyContinue) {{ '
    'try {{ $_ok = & $c -I -c '
    '"import sys;print(int(sys.version_info>=({min_maj},{min_min})))" '
    '2>$null; if ($_ok -eq "1") {{ $_interp = $c; break }} }} '
    'catch {{}} }} }}; '
    'if (-not $_interp) {{ '
    '[Console]::Error.WriteLine("$_warn No suitable Python interpreter found '
    '(need >= {min_maj}.{min_min}). '
    'Install: https://www.python.org/downloads/"); exit 0 }}; '
    # Dispatcher must be a leaf file AND readable. Test-Path alone answers
    # only "does it exist": a file blocked by Windows ACLs passes it, Python
    # then exits 2 opening it, and the trailing `exit $LASTEXITCODE` denies
    # every call. The bash form already checks -r, so testing existence only
    # here left the two launchers covering different failures on the platform
    # the customer was actually running. Refs #4672.
    '$_script = "$_ptr/hooks/{event}/_dispatch.py"; '
    'if (-not (Test-Path $_script -PathType Leaf)) {{ '
    '[Console]::Error.WriteLine("$_warn Dispatcher missing or not a file: '
    '$_script. '
    'Reinstall: copilot plugin install project-toolkit@ai-agents"); exit 0 }}; '
    'try {{ [System.IO.File]::OpenRead($_script).Close() }} catch {{ '
    '[Console]::Error.WriteLine("$_warn Dispatcher not readable: $_script. '
    'Reinstall: copilot plugin install project-toolkit@ai-agents"); exit 0 }}; '
    '& $_interp -I -u "$_script"; '
    'if ($LASTEXITCODE -eq 126 -or $LASTEXITCODE -eq 127) {{ '
    '[Console]::Error.WriteLine("$_warn Python interpreter failed to start '
    '($_interp, exit $LASTEXITCODE). '
    'Install Python >= {min_maj}.{min_min}: '
    'https://www.python.org/downloads/"); exit 0 }}; '
    'exit $LASTEXITCODE'
)

_ENTRYPOINT = """\
from __future__ import annotations

# AUTO-GENERATED HOOK DISPATCHER ENTRYPOINT (ADR-068, #2295).
# Runs every registered matcher shim for this event in ONE process. DO NOT EDIT
# BY HAND; regenerated by build/scripts/generate_dispatcher.py.
# Exit codes: 0 allows the tool call, any non-zero code denies it. A gate-mode
# dispatcher returns the FIRST denying shim's own exit code, which is not
# necessarily 2; 2 is what the dispatcher itself returns when a registered shim
# is missing or dispatch fails. An observer-mode dispatcher always returns 0.
import json
import sys
from pathlib import Path, PureWindowsPath
from typing import cast

# Version check: degrade gracefully on interpreters below the supported floor.
# This runs inside the already-started Python process (no extra subprocess).
# Python 3.7+ can parse this file; older versions fail at `from __future__`.
if sys.version_info < (__MIN_PYTHON_MAJOR__, __MIN_PYTHON_MINOR__):
    _v = ".".join(str(x) for x in sys.version_info[:3])
    print(
        "project-toolkit@ai-agents WARNING: hooks DISABLED (your session is "
        "unaffected). Python >= __MIN_PYTHON_MAJOR__.__MIN_PYTHON_MINOR__ "
        "required but Python " + _v + " found. "
        "Upgrade: https://www.python.org/downloads/",
        file=sys.stderr,
    )
    sys.exit(0)

sys.path.insert(0, str(Path(__file__).resolve().parent))


sys.path.insert(0, str(Path(__file__).resolve().parent))

# Defensive hook-payload ceiling (#3074, ADR-066, CWE-400). Long-session
# apply_patch calls can cross a few MiB, and no measured host maximum exists.
# Below this independent operating limit, unmatched tools allow and registered
# shims enforce their own matcher and replay policies. Above it, gate events deny
# and observe events allow without dispatching a truncated payload.
_MAX_STDIN_BYTES = __HOOK_STDIN_CEILING_MIB__ * 1024 * 1024
_GATE_EVENTS = ("PreToolUse", "preToolUse")
_ADVISE_EVENTS = ("PermissionRequest", "permissionRequest")
# The event this dispatcher was generated for, baked in at generation time.
# The manifest 'event' must equal it exactly before any mode selection, so
# editing the manifest cannot rebind a gate dispatcher to an observer event
# and convert a fail-closed gate into fail-open behavior (#3200, #3074).
_GENERATED_EVENT = __GENERATED_EVENT__
# Bound manifest-controlled diagnostics. repr() escapes control characters
# (no log injection, CWE-117) and the cap prevents an oversized manifest value
# from emitting unbounded stderr (CWE-400). #3200.
_MAX_DIAG_CHARS = 512


def _diag(value):
    text = repr(value)
    if len(text) > _MAX_DIAG_CHARS:
        return text[:_MAX_DIAG_CHARS] + "...(truncated)"
    return text


def _manifest_event(manifest):
    event = manifest.get("event")
    if not isinstance(event, str):
        raise TypeError("manifest field 'event' must be a string")
    if event != _GENERATED_EVENT:
        raise ValueError(
            "manifest field 'event' must equal the generated event "
            + _diag(_GENERATED_EVENT)
            + ", got "
            + _diag(event)
        )
    return event


def _manifest_shims(manifest):
    shims = manifest["shims"]
    if not isinstance(shims, list):
        raise TypeError("manifest field 'shims' must be a list")
    if not shims:
        raise ValueError("manifest field 'shims' must not be empty")
    return shims


def _validate_shim_names(shims):
    normalized_names = set()
    for shim in shims:
        if not isinstance(shim, str):
            raise TypeError("manifest field 'shims' must contain strings")
        windows_path = PureWindowsPath(shim)
        if (
            not shim
            or shim in (".", "..")
            or "/" in shim
            or "\\\\" in shim
            or "\\x00" in shim
            or windows_path.drive
            or Path(shim).suffix.casefold() != ".py"
        ):
            raise ValueError(
                "manifest field 'shims' must contain single basenames ending in .py, got "
                + _diag(shim)
            )
        normalized_name = shim.casefold()
        if normalized_name in normalized_names:
            raise ValueError("manifest field 'shims' must contain unique names")
        normalized_names.add(normalized_name)
    return shims


def _manifest_mode(manifest, event):
    # Default to gate so an older manifest fails closed (ADR-066).
    mode = manifest.get("mode", "gate")
    if mode not in ("gate", "observe", "advise"):
        raise ValueError(
            "manifest field 'mode' must be 'gate', 'observe', or 'advise', "
            f"got {mode!r}"
        )
    if event in _ADVISE_EVENTS:
        expected_mode = "advise"
    elif event in _GATE_EVENTS:
        expected_mode = "gate"
    else:
        expected_mode = "observe"
    if mode != expected_mode:
        raise ValueError(
            f"manifest field 'mode' for {event} must be {expected_mode!r}, got {mode!r}"
        )
    return mode


def _manifest_timeouts(manifest, shims):
    # Metadata supports host budgeting. The host owns the process timeout.
    timeouts = manifest.get("timeouts", {})
    if not isinstance(timeouts, dict):
        raise TypeError("manifest field 'timeouts' must be a dict when present")
    shim_timeouts = {}
    for shim in shims:
        if not isinstance(shim, str):
            raise TypeError("manifest field 'shims' must contain strings")
        if shim not in timeouts:
            continue
        timeout_value = timeouts[shim]
        # Accept only a positive, non-boolean JSON integer. int(True) is 1 and
        # int(3.9)/int("5") silently coerce, so a bool, float, or numeric string
        # must be rejected rather than coerced (#3200).
        if isinstance(timeout_value, bool) or not isinstance(timeout_value, int):
            raise TypeError(
                "manifest timeout for " + _diag(shim)
                + " must be a non-boolean integer, got " + _diag(timeout_value)
            )
        if timeout_value <= 0:
            raise ValueError(
                "manifest timeout for " + _diag(shim) + " must be positive"
            )
        shim_timeouts[shim] = timeout_value
    return shim_timeouts


def _load_manifest(event_dir):
    manifest = json.loads((event_dir / "_manifest.json").read_text(encoding="utf-8"))
    event = _manifest_event(manifest)
    shims = _manifest_shims(manifest)
    mode = _manifest_mode(manifest, event)
    _validate_shim_names(shims)
    return event, shims, _manifest_timeouts(manifest, shims), mode


def _read_payload(
    event: str,
    shims: list[str],
    mode: str,
) -> tuple[bytes, int | None]:
    raw = sys.stdin.buffer.read(_MAX_STDIN_BYTES + 1)
    if len(raw) <= _MAX_STDIN_BYTES:
        return raw, None
    verdict = (
        "denying (fail-closed)"
        if mode in ("gate", "advise")
        else "allowing (observe mode does not gate)"
    )
    print(
        f"hook-dispatch-entrypoint: stdin exceeds {_MAX_STDIN_BYTES} bytes "
        f"for event {_diag(event)} shims={_diag(shims)}; {verdict}",
        file=sys.stderr,
    )
    return raw, 2 if mode in ("gate", "advise") else 0


def _main() -> int:
    event_dir = Path(__file__).resolve().parent
    mode = None
    try:
        from _bootstrap import ensure_plugin_paths  # noqa: E402
        ensure_plugin_paths()
    except (Exception, SystemExit) as exc:
        # Infrastructure failure: the dispatch machinery could not load.
        # Catches ImportError (missing/broken _bootstrap.py, version skew),
        # PluginInfrastructureError (lib dir missing, plugin root invalid),
        # TypeError (signature mismatch from partial upgrade), OSError (file
        # system issues).
        #
        # SystemExit is caught here on purpose. It is a BaseException, so a
        # bare `except Exception` misses it, and every _bootstrap.py shipped
        # before this change calls sys.exit(2) for a missing plugin root or
        # lib directory. A partial upgrade pairing this dispatcher with one of
        # those therefore exited 2 and denied every PreToolUse call: the exact
        # customer-wide denial this fail-open path exists to prevent, arriving
        # through the one exception type the handler did not cover.
        #
        # The scope is deliberately this bootstrap import only. A SystemExit
        # raised later, from shim execution, must still deny, because
        # degrading there would convert "crash the guard" into "bypass the
        # guard".
        # Allow the tool call (exit 0) to keep the plugin usable. A plugin
        # that denies every call forces uninstall, removing all protection.
        # Fail-open on infrastructure keeps the plugin installed so the next
        # release still protects the user (#4672).
        print(
            "project-toolkit@ai-agents WARNING: hooks DISABLED "
            "(your session is unaffected). "
            f"{type(exc).__name__}: {_diag(str(exc))}. "
            "Reinstall the plugin or install Python >= 3.10: "
            "https://www.python.org/downloads/",
            file=sys.stderr,
        )
        return 0
    # The module import is its own infrastructure boundary. Folding it into
    # the dispatch try below meant only ImportError counted as a load failure,
    # so a hook_dispatch.py that exists but cannot compile, cannot be read, or
    # raises during module initialization fell through to the broad handler and
    # was classified as a policy failure: exit 2, denying every PreToolUse
    # call. That is the customer-wide denial arriving through a second door.
    # A load failure cannot be a policy decision, because no policy ran.
    try:
        from hook_dispatch import observe_output_policy, run_dispatch  # noqa: E402
    except (Exception, SystemExit) as exc:
        print(
            "project-toolkit@ai-agents WARNING: hooks DISABLED "
            "(your session is unaffected). "
            f"{type(exc).__name__}: {_diag(str(exc))}. "
            "Reinstall the plugin or install Python >= 3.10: "
            "https://www.python.org/downloads/",
            file=sys.stderr,
        )
        return 0

    try:
        event, shims, shim_timeouts, mode = _load_manifest(event_dir)
        raw, oversize_exit = _read_payload(event, shims, mode)
        if oversize_exit is not None:
            return oversize_exit
        if mode == "advise":
            from hook_dispatch import run_permission_dispatch  # noqa: E402

            return cast(
                int,
                run_permission_dispatch(event_dir, shims, raw, shim_timeouts),
            )
        return cast(
            int,
            run_dispatch(
                event_dir,
                shims,
                raw,
                shim_timeouts,
                short_circuit=mode == "gate",
                output_policy=(
                    observe_output_policy(event) if mode == "observe" else "passthrough"
                ),
            ),
        )
    except ImportError as exc:
        # A nested import inside the dispatch path (run_permission_dispatch)
        # can still fail after the module loaded. Same reasoning: a missing
        # module is infrastructure, not a policy decision.
        print(
            "project-toolkit@ai-agents WARNING: hooks DISABLED "
            "(your session is unaffected). "
            f"{type(exc).__name__}: {_diag(str(exc))}. "
            "Reinstall the plugin or install Python >= 3.10: "
            "https://www.python.org/downloads/",
            file=sys.stderr,
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - generated entrypoint must stay loud
        # Policy or dispatch error after machinery loaded: a shim ran and
        # raised, or manifest validation failed post-load. Fail closed for
        # gate/advise events (these are policy decisions), allow for observers.
        fail_closed = mode in ("gate", "advise") or event_dir.name.lower() in (
            "pretooluse",
            "permissionrequest",
        )
        consequence = (
            "denying (fail-closed)"
            if fail_closed
            else "observer failed; host continues"
        )
        print(
            f"hook-dispatch-entrypoint: {type(exc).__name__}: "
            f"{_diag(str(exc))}; {consequence}",
            file=sys.stderr,
        )
        return 2


sys.exit(_main())
"""
_ENTRYPOINT = _ENTRYPOINT.replace("__HOOK_STDIN_CEILING_MIB__", str(HOOK_STDIN_CEILING_MIB))
_ENTRYPOINT = _ENTRYPOINT.replace("__MIN_PYTHON_MAJOR__", str(_MIN_PYTHON_MAJOR))
_ENTRYPOINT = _ENTRYPOINT.replace("__MIN_PYTHON_MINOR__", str(_MIN_PYTHON_MINOR))


def dispatcher_entry(event: str, timeout_sec: int, matcher: str | None = None) -> dict[str, Any]:
    """Return the single hooks.json entry that registers the event dispatcher.

    ``matcher`` (when not ``None``) is emitted on the entry so hosts with
    host-side matcher filtering skip the dispatcher spawn entirely for
    non-matching tool calls. Verified empirically on Copilot CLI 1.0.71 and
    rechecked on 1.0.72-1: a PascalCase ``PreToolUse`` entry with matcher
    ``Bash`` fired on a Bash tool call while nonmatching entries never spawned.
    Hosts without matcher support ignore the field and fall back to the
    dispatcher's in-process filtering (unchanged).
    """
    entry: dict[str, Any] = {
        "bash": _BASH_TEMPLATE.format(
            event=event, min_maj=_MIN_PYTHON_MAJOR, min_min=_MIN_PYTHON_MINOR
        ),
        "cwd": ".",
        "powershell": _PWSH_TEMPLATE.format(
            event=event, min_maj=_MIN_PYTHON_MAJOR, min_min=_MIN_PYTHON_MINOR
        ),
        "timeoutSec": timeout_sec,
        "type": "command",
    }
    if matcher:
        entry["matcher"] = matcher
    return entry


# Events whose entries accept a host-side matcher per the Copilot hooks
# reference (docs.github.com/en/copilot/reference/hooks-reference,
# "Matcher filtering"), in this generator's PascalCase event names.
_MATCHER_EVENTS = frozenset({"PreToolUse", "PostToolUse", "PermissionRequest"})

# Claude core tool names whose Copilot runtime mapping is documented
# ("Tool names for hook matching"). Only these may appear in an emitted
# host-side matcher union: an unknown token (an MCP tool name, a custom
# regex) could silently never match the runtime name, which would turn a
# registered guard into a dead hook on Copilot. Reduction fails open to
# "no matcher" (dispatcher fires on every call, in-process filter decides,
# exactly the pre-#3075 behavior).
_KNOWN_CLAUDE_TOOLS = frozenset(
    {"Bash", "Edit", "Write", "Read", "Grep", "Glob", "Task", "Agent", "WebFetch"}
)

_TOOL_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_COMMAND_SCOPED_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\(")
_ANCHORED_ALT_RE = re.compile(r"^\^\((.*)\)\$$")


def _matcher_tool_tokens(matcher: str | None) -> list[str] | None:
    """Reduce one Claude matcher to the tool names it can fire for.

    Returns ``None`` when the matcher cannot be safely reduced (empty,
    wildcard, or any token outside ``_KNOWN_CLAUDE_TOOLS``).
    """
    if not matcher or matcher in ("*", "**"):
        return None
    text = str(matcher)
    command_scoped = _COMMAND_SCOPED_RE.match(text)
    if command_scoped:
        tool = command_scoped.group(1)
        return [tool] if tool in _KNOWN_CLAUDE_TOOLS else None
    anchored = _ANCHORED_ALT_RE.match(text)
    inner = anchored.group(1) if anchored else text
    tokens = inner.split("|")
    if all(_TOOL_TOKEN_RE.match(token) and token in _KNOWN_CLAUDE_TOOLS for token in tokens):
        return tokens
    return None


def event_matcher_union(event: str, matchers: list[str | None]) -> str | None:
    """Compute the host-side matcher union for one event's shim matchers.

    Returns a ``|``-joined union of tool names when EVERY registered shim's
    matcher reduces to known tools, else ``None`` (emit no matcher; the
    dispatcher fires on every call and filters in-process).
    """
    if event not in _MATCHER_EVENTS:
        return None
    union: list[str] = []
    for matcher in matchers:
        tokens = _matcher_tool_tokens(matcher)
        if tokens is None:
            return None
        for token in tokens:
            if token not in union:
                union.append(token)
    return "|".join(union) if union else None


def write_manifest(
    event_dir: Path,
    event: str,
    shim_names: list[str],
    shim_timeouts: dict[str, int] | None = None,
    *,
    mode: str = "gate",
) -> Path:
    """Write the ordered shim manifest next to the shims; return its path.

    ``mode`` is ``"gate"`` (short-circuit, fail-closed; ``PreToolUse``),
    ``"advise"`` (one translated ``PermissionRequest`` producer), or
    ``"observe"`` (run every shim, never gate; the other events). The
    entrypoint reads it to choose ``run_dispatch``'s ``short_circuit`` flag.
    ``shim_timeouts`` are carried for manifest validation and cumulative host
    timeout budgeting; they are not enforced inside the dispatcher process.
    """
    if mode not in ("gate", "observe", "advise"):
        raise ValueError(f"mode must be 'gate', 'observe', or 'advise', got {mode!r}")
    manifest_path = event_dir / "_manifest.json"
    manifest: dict[str, Any] = {
        "event": event,
        "mode": mode,
        "shims": list(shim_names),
    }
    if shim_timeouts is not None:
        manifest["timeouts"] = {
            name: int(shim_timeouts[name]) for name in shim_names if name in shim_timeouts
        }
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


# Canonical _bootstrap.py. The dispatcher entrypoint imports
# ``ensure_plugin_paths`` from a sibling ``_bootstrap.py``; only the PreToolUse
# source dir ships one, so every consolidated event dir gets a copy of THIS file
# (single source of truth: copy, never re-author).
_CANONICAL_BOOTSTRAP = (
    Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse" / "_bootstrap.py"
)


def _copy_bootstrap(event_dir: Path) -> Path:
    """Copy the canonical ``_bootstrap.py`` into ``event_dir``; return its path.

    The entrypoint does ``from _bootstrap import ensure_plugin_paths`` after
    inserting its own dir on ``sys.path``, so a copy must sit next to every
    ``_dispatch.py``. Copying from one canonical source avoids N drifting copies.
    """
    dest = event_dir / "_bootstrap.py"
    shutil.copyfile(_CANONICAL_BOOTSTRAP, dest)
    return dest


def write_entrypoint(event_dir: Path, event: str) -> Path:
    """Write the dispatcher entrypoint next to the shims; return its path.

    ``event`` is baked into the entrypoint as ``_GENERATED_EVENT`` (via a
    ``repr`` so any event string is a safe Python literal), so the generated
    dispatcher rejects any manifest whose ``event`` field differs from the
    event it was generated for before any mode selection (#3200).
    """
    entry_path = event_dir / "_dispatch.py"
    source = _ENTRYPOINT.replace("__GENERATED_EVENT__", repr(event))
    entry_path.write_text(source, encoding="utf-8")
    return entry_path


def emit_dispatcher(
    event_dir: Path,
    event: str,
    shim_names: list[str],
    timeout_sec: int,
    shim_timeouts: dict[str, int] | None = None,
    *,
    mode: str = "gate",
    matcher: str | None = None,
) -> dict[str, Any]:
    """Write manifest + entrypoint + bootstrap and return the hooks.json entry.

    ``timeout_sec`` should be the sum of the per-shim timeouts the dispatcher
    replaces, so the consolidated entry preserves the cumulative budget from
    the separate host invocations. ``mode`` is ``"gate"`` (``PreToolUse``,
    fail-closed short-circuit), ``"advise"`` (one translated permission
    producer), or ``"observe"`` (all shims run, never gate).
    ``matcher`` (optional) is the host-side tool-name union for the entry.
    """
    write_manifest(event_dir, event, shim_names, shim_timeouts, mode=mode)
    write_entrypoint(event_dir, event)
    _copy_bootstrap(event_dir)
    return dispatcher_entry(event, timeout_sec, matcher)


# Tool-gating events short-circuit on the first denial (fail-closed).
# PermissionRequest has one translated decision producer. Safely consolidatable
# observers run every shim and never gate. Structured-output events that lack an
# event-specific merger remain direct. PostToolUseFailure also remains direct
# because its exit-2 stdout has host-defined recovery-context semantics. Both
# casings are handled because Copilot event-name casing differs across generations.
_GATE_EVENTS = ("PreToolUse", "preToolUse")
_ADVISE_EVENTS = ("PermissionRequest", "permissionRequest")
_SAFE_OBSERVE_EVENTS = frozenset(
    {
        "PostToolUse",
        "PreCompact",
        "SessionStart",
        "UserPromptSubmit",
        "UserPromptSubmitted",
        "postToolUse",
        "preCompact",
        "sessionStart",
        "userPromptSubmit",
        "userPromptSubmitted",
    }
)
_DEFAULT_TIMEOUT_SEC = 5
_DISPATCHER_TIMEOUT_HEADROOM_SEC = 5
_SCRIPT_RE = re.compile(r"/hooks/[^/]+/([^/\"']+\.py)(?!\.\w)")
_CASE_INSENSITIVE_SHIM_NAMES = os.name == "nt"
_DISPATCHER_CORE_NAMES = ("_manifest.json", "_dispatch.py", "_bootstrap.py")
_DIRECT_HOST_MERGE_EVENTS = frozenset(
    {
        # Stop is the configured compatibility target. The native aliases and
        # SubagentStop variants are defensive exclusions if future mappings use
        # those names. The current source tree has no SubagentStop registration.
        "Stop",
        "stop",
        "agentStop",
        "PostToolUseFailure",
        "postToolUseFailure",
        "SubagentStop",
        "subagentStop",
    }
)


def _mode_for_event(event: str) -> str | None:
    """Return the dispatcher policy for a classified target event."""
    if event in _ADVISE_EVENTS:
        return "advise"
    if event in _GATE_EVENTS:
        return "gate"
    if event in _SAFE_OBSERVE_EVENTS:
        return "observe"
    return None


def _shim_basename(command: str) -> str | None:
    """Extract the ``<name>.py`` basename from a generated hook command."""
    match = _SCRIPT_RE.search(command or "")
    return match.group(1) if match else None


def _dispatcher_shim_entries(
    entries: list[dict[str, Any]],
) -> list[tuple[str, int]]:
    """Return generated shim names and their timeout budgets."""
    return [
        (name, int(entry.get("timeoutSec", _DEFAULT_TIMEOUT_SEC)))
        for entry in entries
        if (name := _shim_basename(entry.get("bash", "")))
    ]


def _shim_name_key(name: str) -> str:
    if _CASE_INSENSITIVE_SHIM_NAMES:
        return name.casefold()
    return name


def validate_event_name(event: str) -> None:
    """Reject hook event names that can escape their output directory."""
    if not event or event in {".", ".."} or "/" in event or "\\" in event or "\x00" in event:
        raise ValueError(f"invalid hook event {event!r}: expected a single path component")


def _resolve_within(path: Path, root: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"could not resolve {label} {path}: {exc}") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes hooks root: {path}") from exc
    return resolved


def validate_event_directory(
    event_dir: Path,
    *,
    hooks_root: Path | None = None,
) -> tuple[Path, Path] | None:
    """Validate a generated hook event directory before any candidate scan.

    Returns ``(resolved_event_dir, root_path)`` when ``event_dir`` is a real,
    non-symlinked directory that resolves inside ``root_path`` (``hooks_root``
    when given, else ``event_dir.parent.resolve(strict=True)``). Returns
    ``None`` when ``event_dir`` does not exist: callers treat a missing event
    directory as "nothing to clean up", not an error. Raises ``ValueError``
    when ``event_dir`` is a symlink, is not a directory, or resolves outside
    ``root_path`` -- a symlinked event directory could otherwise redirect a
    later delete or read into a path outside the generated hook tree
    (CWE-59, symlink following).

    This is the shared safety gate for every generator path that reads or
    deletes candidate files inside a generated hook event directory:
    :func:`find_stale_matcher_shims` below, and
    ``generate_hooks_events._missing_owner_companion_targets`` (issue #5013
    review fix), which reuses this exact sequence instead of maintaining a
    second copy of the lstat/symlink/resolve checks.
    """
    try:
        event_stat = event_dir.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(event_stat.st_mode):
        raise ValueError(f"refusing symlinked event directory: {event_dir}")
    if not stat.S_ISDIR(event_stat.st_mode):
        raise ValueError(f"hook event path is not a directory: {event_dir}")

    try:
        root_path = hooks_root or event_dir.parent.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"could not resolve hooks root for {event_dir}: {exc}") from exc
    resolved_event = _resolve_within(event_dir, root_path, "hook event directory")
    return resolved_event, root_path


def validate_candidate_file(
    candidate: Path,
    resolved_event_dir: Path,
    root_path: Path,
) -> bool:
    """Validate one candidate file inside an already-validated event directory.

    Returns ``True`` when ``candidate`` exists as a regular file that
    resolves inside BOTH ``resolved_event_dir`` and ``root_path`` (the pair
    returned by :func:`validate_event_directory`). Returns ``False`` when the
    candidate does not exist or is not a regular file (a directory, FIFO,
    etc.): callers treat that as "no candidate to act on". Raises
    ``ValueError`` when the candidate is a symlink, which could otherwise
    redirect a delete or read into a path outside the generated hook tree
    (CWE-59, symlink following) -- the same threat :func:`validate_event_directory`
    guards against for the containing directory.
    """
    try:
        candidate_stat = candidate.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(candidate_stat.st_mode):
        raise ValueError(f"refusing symlinked hook candidate: {candidate}")
    if not stat.S_ISREG(candidate_stat.st_mode):
        return False
    _resolve_within(candidate, resolved_event_dir, "hook candidate")
    _resolve_within(candidate, root_path, "hook candidate")
    return True


def find_stale_matcher_shims(
    event_dir: Path,
    shim_names: list[str],
    *,
    hooks_root: Path | None = None,
) -> list[Path]:
    """Return removable generated shims omitted from the manifest."""
    validated = validate_event_directory(event_dir, hooks_root=hooks_root)
    if validated is None:
        return []
    resolved_event, root_path = validated
    active_shims = {_shim_name_key(name) for name in shim_names}
    stale_shims: list[Path] = []
    for candidate in sorted(event_dir.iterdir()):
        if not validate_candidate_file(candidate, resolved_event, root_path):
            continue
        if candidate.suffix != ".py":
            continue
        if _shim_name_key(candidate.name) in active_shims:
            continue
        source = candidate.read_text(encoding="utf-8")
        if not is_shimmed(source):
            continue
        reason = regen_detect_reason(candidate)
        if reason is not None:
            print(f"  NOTICE: skipped {candidate} (NO-REGEN: {reason})")
            continue
        stale_shims.append(candidate)
    return stale_shims


def _read_orphan_manifest(event_dir: Path) -> dict[str, Any] | None:
    manifest_path = event_dir / "_manifest.json"
    try:
        candidate_stat = manifest_path.lstat()
        if stat.S_ISLNK(candidate_stat.st_mode) or not stat.S_ISREG(candidate_stat.st_mode):
            raise ValueError("manifest is not a regular file")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(
            f"  NOTICE: preserved orphan hook directory {event_dir} "
            f"(ownership manifest invalid: {exc})"
        )
        return None
    shims = manifest.get("shims") if isinstance(manifest, dict) else None
    if (
        not isinstance(manifest, dict)
        or manifest.get("event") != event_dir.name
        or not isinstance(shims, list)
        or not all(isinstance(name, str) for name in shims)
    ):
        print(
            f"  NOTICE: preserved orphan hook directory {event_dir} "
            "(ownership manifest does not match the directory)"
        )
        return None
    return manifest


def _verified_orphan_file(
    candidate: Path,
    event_dir: Path,
    hooks_root: Path,
    *,
    expected_bytes: bytes | None = None,
    require_shim: bool = False,
) -> bool:
    try:
        candidate_stat = candidate.lstat()
        if stat.S_ISLNK(candidate_stat.st_mode) or not stat.S_ISREG(candidate_stat.st_mode):
            return False
        _resolve_within(candidate, event_dir, "orphan hook artifact")
        _resolve_within(candidate, hooks_root, "orphan hook artifact")
        content = candidate.read_bytes()
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        return False
    if expected_bytes is not None:
        return content == expected_bytes
    if require_shim:
        try:
            return bool(is_shimmed(content.decode("utf-8")))
        except UnicodeError:
            return False
    return True


def _verified_dispatcher_signature(
    candidate: Path,
    event_dir: Path,
    hooks_root: Path,
    expected_bytes: bytes,
) -> bool:
    """Accept the current dispatcher bytes or the prior generated signature."""
    if _verified_orphan_file(
        candidate,
        event_dir,
        hooks_root,
        expected_bytes=expected_bytes,
    ):
        return True
    if not _verified_orphan_file(candidate, event_dir, hooks_root):
        return False
    try:
        source = candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    signatures = (
        "AUTO-GENERATED HOOK DISPATCHER ENTRYPOINT (ADR-068, #2295).",
        f"_GENERATED_EVENT = {event_dir.name!r}",
        "from _bootstrap import ensure_plugin_paths",
        "sys.exit(_main())",
    )
    return all(signature in source for signature in signatures)


class _DocstringStripper(ast.NodeTransformer):
    """Remove docstrings so comment-only canonical edits retain ownership proof."""

    def _strip(
        self,
        node: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    ) -> ast.AST:
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:]
        return self.generic_visit(node)

    def visit_Module(self, node: ast.Module) -> ast.AST:
        return self._strip(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        return self._strip(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self._strip(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        return self._strip(node)


def _python_program_signature(path: Path) -> str | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError):
        return None
    stripped = _DocstringStripper().visit(tree)
    return ast.dump(stripped, include_attributes=False)


def _matches_canonical_source(candidate: Path, source_hooks: Path | None) -> bool:
    """Prove a matcher-free generated copy against its canonical Python body."""
    if source_hooks is None:
        return False
    candidate_signature = _python_program_signature(candidate)
    if candidate_signature is None:
        return False
    try:
        sources = source_hooks.rglob(candidate.name)
    except OSError:
        return False
    return any(
        source.is_file() and _python_program_signature(source) == candidate_signature
        for source in sources
    )


def _orphan_bytecode_targets(
    event_dir: Path, owned_python: set[str], hooks_root: Path
) -> tuple[list[Path], list[Path]]:
    cache_dir = event_dir / "__pycache__"
    try:
        cache_stat = cache_dir.lstat()
    except FileNotFoundError:
        return [], []
    if stat.S_ISLNK(cache_stat.st_mode) or not stat.S_ISDIR(cache_stat.st_mode):
        print(f"  NOTICE: preserved unknown orphan cache {cache_dir}")
        return [], []
    try:
        resolved_cache = _resolve_within(cache_dir, hooks_root, "orphan bytecode cache")
    except ValueError:
        print(f"  NOTICE: preserved unsafe orphan cache {cache_dir}")
        return [], []
    targets: list[Path] = []
    for candidate in sorted(cache_dir.iterdir()):
        stem_match = any(
            candidate.name.startswith(f"{Path(source).stem}.cpython-")
            and candidate.suffix == ".pyc"
            for source in owned_python
        )
        if not stem_match or not _verified_orphan_file(candidate, resolved_cache, hooks_root):
            print(f"  NOTICE: preserved unknown orphan cache artifact {candidate}")
            return [], []
        targets.append(candidate)
    return targets, [cache_dir]


def _resolve_orphan_event(event_dir: Path, hooks_root: Path) -> Path | None:
    try:
        event_stat = event_dir.lstat()
    except OSError as exc:
        print(f"  NOTICE: preserved unreadable orphan path {event_dir}: {exc}")
        return None
    if stat.S_ISLNK(event_stat.st_mode) or not stat.S_ISDIR(event_stat.st_mode):
        return None
    try:
        return _resolve_within(event_dir, hooks_root, "orphan hook event directory")
    except ValueError as exc:
        print(f"  NOTICE: preserved unsafe orphan hook directory {event_dir}: {exc}")
        return None


def _verified_orphan_core(
    event_dir: Path,
    resolved_event: Path,
    hooks_root: Path,
) -> tuple[dict[str, Any], list[Path]] | None:
    manifest = _read_orphan_manifest(event_dir)
    if manifest is None:
        return None
    dispatch_path = event_dir / "_dispatch.py"
    bootstrap_path = event_dir / "_bootstrap.py"
    expected_dispatch = _ENTRYPOINT.replace("__GENERATED_EVENT__", repr(event_dir.name)).encode(
        "utf-8"
    )
    dispatch_verified = _verified_dispatcher_signature(
        dispatch_path,
        resolved_event,
        hooks_root,
        expected_dispatch,
    )
    bootstrap_verified = _verified_orphan_file(
        bootstrap_path,
        resolved_event,
        hooks_root,
        expected_bytes=_CANONICAL_BOOTSTRAP.read_bytes(),
    )
    if not dispatch_verified or not bootstrap_verified:
        print(
            f"  NOTICE: preserved orphan hook directory {event_dir} (dispatcher signature mismatch)"
        )
        return None
    owned = [event_dir / "_manifest.json", dispatch_path, bootstrap_path]
    return manifest, owned


def _verified_orphan_shims(
    event_dir: Path,
    resolved_event: Path,
    hooks_root: Path,
    shim_names: list[str],
    source_hooks: Path | None,
) -> list[Path] | None:
    shim_paths = [event_dir / name for name in shim_names]
    verified = all(
        Path(name).name == name
        and (
            _verified_orphan_file(
                candidate,
                resolved_event,
                hooks_root,
                require_shim=True,
            )
            or _matches_canonical_source(candidate, source_hooks)
        )
        for name, candidate in zip(shim_names, shim_paths, strict=True)
    )
    if verified:
        return shim_paths
    print(
        f"  NOTICE: preserved orphan hook directory {event_dir} "
        "(manifest-listed shim ownership failed)"
    )
    return None


def _collect_orphan_event(
    event_dir: Path,
    hooks_root: Path,
    source_hooks: Path | None,
) -> tuple[list[Path], list[Path]]:
    resolved_event = _resolve_orphan_event(event_dir, hooks_root)
    if resolved_event is None:
        return [], []
    core = _verified_orphan_core(event_dir, resolved_event, hooks_root)
    if core is None:
        return [], []
    manifest, owned = core
    shim_paths = _verified_orphan_shims(
        event_dir,
        resolved_event,
        hooks_root,
        manifest["shims"],
        source_hooks,
    )
    if shim_paths is None:
        return [], []
    owned.extend(shim_paths)
    bytecode, cache_dirs = _orphan_bytecode_targets(
        event_dir,
        {path.name for path in owned if path.suffix == ".py"},
        hooks_root,
    )
    owned.extend(bytecode)
    protected: list[tuple[Path, str]] = []
    for candidate in owned:
        reason = regen_detect_reason(candidate)
        if reason is not None:
            protected.append((candidate, reason))
    if protected:
        for candidate, reason in protected:
            print(f"  NOTICE: preserved {candidate} (NO-REGEN: {reason})")
        return [], []
    known_paths = set(owned) | set(cache_dirs)
    for candidate in sorted(event_dir.iterdir()):
        if candidate not in known_paths:
            print(f"  NOTICE: preserved unknown orphan artifact {candidate}")
    return owned, [*cache_dirs, event_dir]


def find_owned_orphan_artifacts(
    hooks_dir: Path,
    active_events: set[str],
    *,
    source_hooks: Path | None = None,
) -> tuple[list[Path], list[Path]]:
    """Find ownership-proven files in generated event dirs no longer active."""
    if not hooks_dir.exists():
        return [], []
    try:
        hooks_stat = hooks_dir.lstat()
        if stat.S_ISLNK(hooks_stat.st_mode) or not stat.S_ISDIR(hooks_stat.st_mode):
            print(f"  NOTICE: preserved unsafe hooks output root {hooks_dir}")
            return [], []
        hooks_root = hooks_dir.resolve(strict=True)
    except (OSError, RuntimeError):
        print(f"  NOTICE: preserved unresolved hooks output root {hooks_dir}")
        return [], []
    targets: list[Path] = []
    directories: list[Path] = []
    for event_dir in sorted(hooks_dir.iterdir()):
        if event_dir.name in active_events:
            continue
        event_targets, event_directories = _collect_orphan_event(
            event_dir,
            hooks_root,
            source_hooks,
        )
        targets.extend(event_targets)
        directories.extend(event_directories)
    return targets, directories


def find_owned_dispatcher_core_artifacts(
    hooks_dir: Path,
    events: set[str],
) -> list[Path]:
    """Return generated dispatcher core files for active direct events.

    A contract change can move an event from consolidated dispatch back to
    separate host registrations. Remove only the signature-verified dispatcher
    manifest, entrypoint, and bootstrap. Keep the event's hook scripts because
    the direct registrations still invoke them.
    """
    if not hooks_dir.exists():
        return []
    try:
        hooks_root = hooks_dir.resolve(strict=True)
    except (OSError, RuntimeError):
        return []
    targets: list[Path] = []
    for event in sorted(events):
        event_dir = hooks_dir / event
        resolved_event = _resolve_orphan_event(event_dir, hooks_root)
        if resolved_event is None:
            continue
        if not any(
            (event_dir / name).exists() or (event_dir / name).is_symlink()
            for name in _DISPATCHER_CORE_NAMES
        ):
            continue
        core = _verified_orphan_core(event_dir, resolved_event, hooks_root)
        if core is None:
            continue
        _manifest, owned = core
        for candidate in owned:
            reason = regen_detect_reason(candidate)
            if reason is None:
                targets.append(candidate)
            else:
                print(f"  NOTICE: preserved {candidate} (NO-REGEN: {reason})")
    return targets


def consolidate(
    out: dict[str, list[dict[str, Any]]], hooks_dir: Path
) -> dict[str, list[dict[str, Any]]]:
    """Collapse safe events' per-shim entries to one dispatcher entry.

    ``out`` is the generator's ``{event: [entry, ...]}`` map. For each safe event
    this writes ``_manifest.json`` + ``_dispatch.py`` + ``_bootstrap.py`` into
    ``hooks_dir/<event>/`` and returns a new map with a single dispatcher entry
    for that event. Classified tool-gating events get ``mode="gate"``
    (fail-closed short-circuit, unchanged from #2295). Explicitly safe observer
    events get ``mode="observe"`` (all shims run, never gate; #2342).
    Unclassified events pass through unchanged so a future event's output
    contract cannot be silently discarded. An event whose entries contain no
    parseable shim path also passes through unchanged. The shim order is the
    registered hooks.json order (authoritative) and the consolidated
    ``timeoutSec`` is the sum of the per-shim timeouts. Stop and SubagentStop
    pass through so the host can merge multiple structured decisions without
    invalid JSON concatenation. PostToolUseFailure also passes through because
    exit 2 converts that hook's stdout to recovery context; the generic observe
    dispatcher intentionally discards nonzero-shim stdout. The consolidated
    ``timeoutSec`` is the sum of per-shim timeouts plus five seconds for
    dispatcher startup, manifest loading, and transitions between shims.
    """
    new_out: dict[str, list[dict[str, Any]]] = {}
    for event, entries in out.items():
        validate_event_name(event)
        if event in _DIRECT_HOST_MERGE_EVENTS:
            new_out[event] = entries
            continue
        shim_entries = _dispatcher_shim_entries(entries)
        if not shim_entries:
            new_out[event] = entries
            continue
        shim_names = [name for name, _ in shim_entries]
        mode = _mode_for_event(event)
        if mode is None:
            new_out[event] = entries
            continue
        if mode == "advise" and len(shim_names) != 1:
            raise ValueError(
                f"PermissionRequest requires exactly one decision producer, got {len(shim_names)}"
            )
        shim_timeouts = dict(shim_entries)
        timeout = (
            sum(timeout_sec for _, timeout_sec in shim_entries) + _DISPATCHER_TIMEOUT_HEADROOM_SEC
        )
        matchers = [entry.get("claudeMatcher") for entry in entries if isinstance(entry, dict)]
        event_dir = Path(hooks_dir) / event
        new_out[event] = [
            emit_dispatcher(
                event_dir,
                event,
                shim_names,
                timeout,
                shim_timeouts,
                mode=mode,
                matcher=event_matcher_union(event, matchers),
            )
        ]
    return new_out
