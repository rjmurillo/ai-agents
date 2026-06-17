#!/usr/bin/env python3
"""Reset stale LSP-gate navigation state at session start (ADR-062 Section 4).

Claude Code SessionStart hook. The trusted lifecycle reset signal for the
conditional LSP-first enforcement layer: it clears the gate-state file for the
resolved project directory so a new session always begins in "needs warmup",
never inheriting
"surgical mode" (nav_count >= NAV_REQUIRED) from prior work.

State is owned by the PostToolUse usage tracker and lives OUTSIDE the git
working tree (``scripts/hook_utilities/lsp_gate_state.py``). This hook only
calls ``reset_state(project_dir)`` for the resolved project directory (from
``get_project_directory()``); reset is idempotent and never
raises (fail-open). Reset is driven solely by this SessionStart signal, not by
agent-controllable input.

Ported from the claude-code-lsp-enforcement-kit (nesaminua, MIT, v2.3.2),
file ``kit/hooks/lsp-session-reset.js``. The kit's reset logic, quoted
character-for-character (canonical-source-mirror.md):

    let cwd = process.cwd();
    try {
      const data = JSON.parse(raw || '{}');
      if (data.cwd && typeof data.cwd === 'string') cwd = data.cwd;
    } catch { /* ignore */ }

    const flagPath = getFlagPath(cwd);

    try {
      if (fs.existsSync(flagPath)) {
        fs.unlinkSync(flagPath);
      }
    } catch { /* silent: hook must never block session start */ }

    process.exit(0);

Kit flag-path scheme (``lsp-session-reset.js:28-33``), quoted verbatim:

    const STATE_DIR = path.join(os.homedir(), '.claude', 'state');
    function getFlagPath(cwd) {
      const hash = crypto.createHash('md5').update(cwd).digest('hex').slice(0, 12);
      return path.join(STATE_DIR, `lsp-ready-${hash}`);
    }

Stricter/looser/different than canonical
----------------------------------------
- DIFFERENT path scheme: the kit unlinks ``~/.claude/state/lsp-ready-<md5[:12]>``.
  This port delegates the path to ``lsp_gate_state.reset_state``, which uses
  ``$XDG_STATE_HOME/ai-agents-lsp-gate`` (else ``~/.cache/ai-agents-lsp-gate``)
  keyed by ``sha256(cwd)[:16]`` per ADR-062 Section 4 (md5 forbidden; state off
  ``~/.claude``). The reset behavior (idempotent, silent, exit 0) is identical.
- ADDED kill switch and mode: this port honors ``SKIP_LSP_GATE=true`` (bypass,
  no reset) and ``LSP_GATE_MODE`` for parity with the other ADR-062 guards. The
  kit had neither. In ``warn`` mode the reset still runs (warn mode only changes
  block-to-advisory on the gating guards; the reset is always a safe no-op-or-clear
  lifecycle action and never blocks).
- SAME guarantee: always exit 0. A SessionStart hook must never block startup
  (ADR-008 fail-open scope, ADR-035 Claude-hook-semantics; SessionStart exit 2
  only surfaces stderr and is never used here).

Hook Type: SessionStart
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Always (reset succeeded, failed silently, skipped, or bypassed).
        SessionStart hooks never block.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Bootstrap: find lib directory via env var or manifest walk-up.
# CLAUDE_PLUGIN_ROOT honored when set; otherwise walk up from __file__
# looking for .claude-plugin/plugin.json (the plugin marker). Sibling
# lib/ is the plugin's lib dir. Layout-independent: works in source
# tree (.claude/) and in the deeper src/<provider>/hooks/<event>/ copy.
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _cur = Path(__file__).resolve().parent
    _lib_dir = None
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print(
        f"Plugin lib directory not found: {_lib_dir} (CLAUDE_PLUGIN_ROOT={_plugin_root!r})",
        file=sys.stderr,
    )
    # Fail-open: SessionStart must never block session startup.
    sys.exit(0)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import get_project_directory  # noqa: E402
from hook_utilities.lsp_gate_state import reset_state  # noqa: E402
from hook_utilities.lsp_health import clear_lsp_down_marker  # noqa: E402


def main() -> int:
    """Main hook entry point. Always returns 0 (SessionStart never blocks)."""
    try:
        # Normalized check for consistent behavior with other ADR-062 guards.
        if os.environ.get("SKIP_LSP_GATE", "").strip().lower() == "true":
            # Kill switch: bypass the gate entirely, leave state untouched.
            print("[SKIP] lsp-session-reset: SKIP_LSP_GATE=true", file=sys.stderr)
            return 0

        # Use get_project_directory() to match the key used by the usage tracker
        # and read guard. Using a different key (e.g. os.getcwd() or JSON cwd)
        # would reset a different state file than the one guards actually use.
        project_dir = get_project_directory()

        try:
            ok = reset_state(project_dir)
        except Exception as exc:  # noqa: BLE001 - marker reset still must run.
            ok = False
            print(
                f"lsp-session-reset state error: {type(exc).__name__} - {exc}",
                file=sys.stderr,
            )
        marker_ok = clear_lsp_down_marker(project_dir)
        mode = os.environ.get("LSP_GATE_MODE", "block")
        print(
            f"lsp-session-reset: reset={ok} marker_cleared={marker_ok} "
            f"mode={mode} key=sha256(project_dir)[:16]",
            file=sys.stderr,
        )
        return 0

    except Exception as exc:  # noqa: BLE001 - SessionStart must never block.
        # Fail-open: a reset failure must not block session startup.
        print(f"lsp-session-reset error: {type(exc).__name__} - {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
