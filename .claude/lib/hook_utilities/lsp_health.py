"""Canonical: scripts/hook_utilities/lsp_health.py. Sync via scripts/sync_plugin_lib.py.

Canonical module. Plugin-distributed copy at
``.claude/lib/hook_utilities/lsp_health.py``; run
``python3 scripts/sync_plugin_lib.py`` to sync.

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

System of record
----------------
The env var ``LSP_DOWN`` is the signal's SoR. The one-time-warning marker is
derived per-session dedup state, rebuildable by definition (deleting it only
re-emits the warning once). The marker lives OUTSIDE the git working tree in the
same user-scoped state dir the gate-state file uses, so it is never committed
and never collides with repo state (mirrors ``lsp_gate_state._state_dir``).

Security (CWE-22, Low): the marker path is derived from a sha256 of the resolved
cwd plus a fixed prefix, never from tool input, so there is no path-traversal
surface. Tampering with the marker only changes whether one advisory line is
printed; it is not a security boundary.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

# Env signal: the explicit "the LSP runtime is down/uninitialized" flag. Mirrors
# the truthy parsing of SKIP_LSP_GATE (case-insensitive ``true``/``1``/``yes``).
LSP_DOWN_ENV = "LSP_DOWN"

_TRUTHY = frozenset({"true", "1", "yes", "on"})

# State subdir for the one-time-warning marker. Same base dir scheme as
# lsp_gate_state so plugin state and gate state share a parent but distinct files.
_STATE_SUBDIR = "ai-agents-lsp-gate"


def lsp_runtime_down() -> bool:
    """Return True when an explicit LSP-down signal is set for this session.

    Pure read of the ``LSP_DOWN`` env var (no live probe, ADR-062 Section 8).
    Truthy values: ``true``/``1``/``yes``/``on`` (case-insensitive). Any other
    value, or an unset var, returns False (the guards enforce as normal).
    """
    return os.environ.get(LSP_DOWN_ENV, "").strip().lower() in _TRUTHY


def _state_dir() -> Path:
    """Return the user-scoped state directory, outside the git working tree.

    Honors ``$XDG_STATE_HOME`` when set, else ``~/.cache``. Mirrors
    ``lsp_gate_state._state_dir`` so the marker never lands in the repo tree.
    """
    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    base = Path(xdg) if xdg else Path.home() / ".cache"
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

    Writes a per-cwd marker the first time it warns; subsequent calls observe
    the marker and stay silent (the issue's "one-time warning instead of
    repeated hard blocks"). Returns True when this call emitted the warning,
    False when it was already emitted or the marker could not be written.

    Any filesystem error degrades to NOT emitting on the failed call rather than
    raising; a navigation gate must never wedge a turn (release-it.md).
    """
    marker = _marker_path(project_dir)
    try:
        if marker.exists():
            return False
    except OSError:
        return False

    message = (
        f"{guard_name}: LSP runtime is down ({LSP_DOWN_ENV} set); allowing native "
        "tools (Read/Edit/Grep). LSP-first enforcement is paused until the "
        "language server recovers."
    )
    print(message, file=sys.stderr)

    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
    except OSError:
        # Could not persist the marker: we already printed once, so degrade to
        # "warned" semantics for this call but allow a future call to warn again.
        return True
    return True


def clear_lsp_down_marker(project_dir: str) -> bool:
    """Remove the one-time-warning marker for ``project_dir``. Idempotent.

    Called by the SessionStart reset so a fresh session warns again if the LSP
    is still down. Returns False only on a filesystem error other than missing.
    """
    try:
        _marker_path(project_dir).unlink(missing_ok=True)
    except OSError:
        return False
    return True
