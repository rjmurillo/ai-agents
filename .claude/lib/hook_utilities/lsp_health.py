"""Canonical: scripts/hook_utilities/lsp_health.py. Sync via scripts/sync_plugin_lib.py.

Canonical source path: ``scripts/hook_utilities/lsp_health.py``.
Synced distribution paths:
``.claude/lib/hook_utilities/lsp_health.py`` and
``src/copilot-cli/lib/hook_utilities/lsp_health.py``. Run
``python3 scripts/sync_plugin_lib.py`` to sync the distribution copies.

WHY THIS EXISTS (issue #2622)
-----------------------------
``lsp_provider.detect_providers`` is a PURE configuration check: a language
listed in ``.serena/project.yml`` with the serena MCP server registered counts
as "available" even when the language server is not actually running this turn
(ADR-062 Section 8, "configured != active"). ADR-062 Section 5 says that gap is
handled at the tool-call boundary by fail-open. Before this module, the Read and
grep guards only failed open on *exceptions*, a *missing provider*, or the
*kill switch*: none of those fire when the markdown language server times out at
startup while config still lists it. The guards then converted a degraded
capability (no symbols) into a hard block on basic Read/Edit/Grep, and the only
escape was a manual ``SKIP_LSP_GATE=true`` for the whole session.

This module adds the missing runtime-health gate. It is NOT a live probe (no
outbound call, no timeout, ADR-062 Section 8 preserved): it reads an EXPLICIT
"LSP is down" signal, the same env-signal shape the guards already use for
``SKIP_LSP_GATE`` and ``LSP_GATE_MODE``. When the signal is set, the guards
ALLOW the tool and emit a one-time warning instead of repeatedly hard-blocking.

The signal is set out-of-band by whatever observes the language-server failure
(the session, a SessionStart probe, or the user reacting to a timeout). Keeping
the producer separate keeps this module a thin, pure reader (clean-architecture):
the guard depends on the signal, not on Serena internals.

Persistent down-signal (issue #3108)
------------------------------------
The env var cannot be applied from a dedicated Read/Edit/Grep/Glob/ApplyPatch
tool call: those schemas carry no env field, and each Bash call runs in a fresh
process, so ``env LSP_DOWN=true`` never reaches the next tool call. That left the
env var usable only from shell replacements the repo forbids. A persistent
per-cwd MARKER FILE fixes the gap: it survives across the fresh processes each
dedicated tool spawns, so an operator sets it once (``set_lsp_down_signal`` or
``python3 lsp_health.py --set-down`` from Bash, which persists the file) and
every subsequent guard honors it. ``lsp_runtime_down`` returns True when EITHER
the env var is truthy OR the marker exists.

System of record
----------------
The env var ``LSP_DOWN`` and the persistent down-signal marker are two producers
of the same "runtime is down" signal; either is sufficient. The one-time-warning
marker is separate per-session dedup state, rebuildable by definition (deleting
it only re-emits the warning once). All markers live OUTSIDE the git working tree
in the same user-scoped state dir the gate-state file uses, so they are never
committed and never collide with repo state (mirrors ``lsp_gate_state._state_dir``).
The down-signal marker is operator-controlled and persists until cleared (``python3
lsp_health.py --clear-down`` or ``clear_lsp_down_signal``), the same lifetime the
``LSP_DOWN`` env var has (it lives until unset). The operator clears it when the
language server recovers.

Security (CWE-22, Low): every marker path is derived from a sha256 of the
resolved cwd plus a fixed prefix, never from tool input, so there is no
path-traversal surface. The down-signal marker only pauses LSP-first enforcement
(it fails open to the SAME degraded behavior the env var already allowed); it is
not an auth or trust boundary, and the guards still enforce normally when it is
absent.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

# Env signal: the explicit "the LSP runtime is down/uninitialized" flag. Mirrors
# the truthy parsing of SKIP_LSP_GATE (case-insensitive ``true``/``1``/``yes``).
LSP_DOWN_ENV = "LSP_DOWN"

_TRUTHY = frozenset({"true", "1", "yes", "on"})

# State subdir for the one-time-warning marker. Same base dir scheme as
# lsp_gate_state so plugin state and gate state share a parent but distinct files.
_STATE_SUBDIR = "ai-agents-lsp-gate"

# Filename prefix for the persistent down-signal marker (issue #3108). Distinct
# from the "lsp-down-warned-" one-time-warning marker: this one IS the signal,
# the other only dedups the advisory line.
_DOWN_SIGNAL_PREFIX = "lsp-down-signal-"


def _down_signal_path(project_dir: str) -> Path:
    """Return the absolute persistent LSP-down signal marker for ``project_dir``."""
    return _state_dir() / f"{_DOWN_SIGNAL_PREFIX}{_cwd_key(project_dir)}"


def lsp_runtime_down(project_dir: str | None = None) -> bool:
    """Return True when an explicit LSP-down signal is set for this session.

    Two producers, either sufficient (issue #2622 env var, issue #3108 marker):

    - the ``LSP_DOWN`` env var, truthy ``true``/``1``/``yes``/``on``
      (case-insensitive); any other value or unset returns False, and
    - a persistent per-cwd down-signal marker file. The env var dies with the
      process, so a dedicated Read/Edit/Grep/Glob/ApplyPatch tool call (no env
      field in its schema, Bash sibling in a fresh process) cannot use it. The
      marker persists across those processes: set once, honored by every later
      guard.

    Pure reads only, no live probe (ADR-062 Section 8). ``project_dir`` defaults
    to the current working directory, the cwd a PreToolUse guard runs in.
    """
    if os.environ.get(LSP_DOWN_ENV, "").strip().lower() in _TRUTHY:
        return True
    target = project_dir if project_dir is not None else os.getcwd()
    try:
        return _down_signal_path(target).exists()
    except (OSError, ValueError):
        return False


def set_lsp_down_signal(project_dir: str | None = None) -> bool:
    """Create the persistent LSP-down signal marker for ``project_dir``. Idempotent.

    ``project_dir`` defaults to the current working directory. Returns False only
    on a filesystem error; a failed set must not wedge a turn (release-it.md).
    """
    target = project_dir if project_dir is not None else os.getcwd()
    try:
        path = _down_signal_path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("1", encoding="utf-8")
    except (OSError, ValueError):
        return False
    return True


def clear_lsp_down_signal(project_dir: str | None = None) -> bool:
    """Remove the persistent LSP-down signal marker for ``project_dir``. Idempotent.

    The operator clears the signal when the language server recovers (via
    ``--clear-down`` or this call). Returns False only on a filesystem error
    other than missing.
    """
    target = project_dir if project_dir is not None else os.getcwd()
    try:
        _down_signal_path(target).unlink(missing_ok=True)
    except (OSError, ValueError):
        return False
    return True


def _state_dir() -> Path:
    """Return the user-scoped state directory, outside the git working tree.

    Honors ``$XDG_STATE_HOME`` when set, else ``~/.cache``. Falls back to
    ``tempfile.gettempdir()`` when both are unavailable (e.g. sandboxed or
    CI environments where ``Path.home()`` raises ``RuntimeError`` because the
    running user has no home directory). Mirrors ``lsp_gate_state._state_dir``
    so the marker never lands in the repo tree.
    """
    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg:
        base = Path(xdg)
    else:
        try:
            base = Path.home() / ".cache"
        except RuntimeError:
            base = Path(tempfile.gettempdir()) / ".cache"
    return base / _STATE_SUBDIR


def _cwd_key(project_dir: str) -> str:
    """Return a stable per-cwd key: sha256(resolved cwd) truncated to 16 hex."""
    try:
        normalized = str(Path(project_dir).resolve())
    except (OSError, ValueError):
        normalized = project_dir
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _marker_path(project_dir: str) -> Path:
    """Return the absolute one-time-warning marker path for ``project_dir``."""
    return _state_dir() / f"lsp-down-warned-{_cwd_key(project_dir)}"


def warn_once_lsp_down(guard_name: str, project_dir: str) -> bool:
    """Emit the LSP-down fail-open warning at most once per session. Never raises.

    Claims a per-cwd marker with exclusive create before it warns; subsequent
    calls observe the marker and stay silent (the issue's "one-time warning
    instead of repeated hard blocks"). Returns True when this call emitted the
    warning (regardless of whether the dedup marker was successfully persisted).
    Returns False when the warning was already emitted this session (marker
    exists).

    Any marker filesystem error degrades to emitting without persistence rather
    than raising; a navigation gate must never wedge a turn (release-it.md).
    """
    try:
        marker = _marker_path(project_dir)
        marker.parent.mkdir(parents=True, exist_ok=True)
        with marker.open("x", encoding="utf-8") as fh:
            fh.write("1")
    except FileExistsError:
        return False
    except (OSError, ValueError):
        marker = None

    message = (
        f"{guard_name}: LSP runtime is down ({LSP_DOWN_ENV} set); allowing this "
        "operation to continue. LSP-first enforcement is paused until the "
        "language server recovers."
    )
    print(message, file=sys.stderr)
    return True


def clear_lsp_down_marker(project_dir: str) -> bool:
    """Remove the one-time-warning marker for ``project_dir``. Idempotent.

    Called by the SessionStart reset so a fresh session warns again if the LSP
    is still down. Returns False only on a filesystem error other than missing.
    """
    try:
        _marker_path(project_dir).unlink(missing_ok=True)
    except (OSError, ValueError):
        return False
    return True


def _main(argv: list[str] | None = None) -> int:
    """CLI to set/clear/query the persistent down-signal from a shell (issue #3108).

    Bash is the one tool that can persist a file across the fresh processes each
    dedicated tool spawns, so this gives an operator a deterministic command to
    flip the signal that Read/Edit/Grep guards then honor. argparse is imported
    lazily so the hot hook-import path does not pay for it.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Set/clear/query the persistent LSP-down signal for the cwd (issue #3108).",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--set-down", action="store_true", help="Create the down-signal marker")
    group.add_argument("--clear-down", action="store_true", help="Remove the down-signal marker")
    group.add_argument("--status", action="store_true", help="Print active or inactive")
    args = parser.parse_args(argv)

    cwd = os.getcwd()
    if args.set_down:
        ok = set_lsp_down_signal(cwd)
        print(f"lsp-down signal set for {cwd}" if ok else "failed to set lsp-down signal")
        return 0 if ok else 1
    if args.clear_down:
        ok = clear_lsp_down_signal(cwd)
        print(f"lsp-down signal cleared for {cwd}" if ok else "failed to clear lsp-down signal")
        return 0 if ok else 1
    print("active" if lsp_runtime_down(cwd) else "inactive")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
