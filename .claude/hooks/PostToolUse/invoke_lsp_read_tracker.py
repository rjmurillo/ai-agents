#!/usr/bin/env python3
"""Track allowed Read operations for the graduated LSP-first gate (ADR-062 Section 4).

Claude Code PostToolUse hook (matcher ``Read``). When the Read guard allows a Read
operation (exit 0), this tracker records the file path via ``record_read`` so the
graduated tiers (soft-allow, soft-warn, hard-block) work correctly. Without this
tracking, ``read_files`` stays empty and every gated Read is treated as read
number 1, so the graduated enforcement never kicks in.

This hook complements the usage tracker (``invoke_lsp_usage_tracker.py``), which
tracks LSP navigation calls. Together they implement ADR-062 Section 4's
single-system-of-record for gate state: navigation via ``record_nav``, reads via
``record_read``, both in PostToolUse.

Hook Type: PostToolUse
Matcher (register in hooks.json): Read
Exit Codes:
    0 = Always. PostToolUse never blocks.

Fail-open (mandatory, ADR-062 Section 5): missing lib, malformed JSON, any error
returns 0 without mutating state. A tracking failure must never block the agent.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Bootstrap: find lib directory via env var or manifest walk-up.
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
    sys.exit(0)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import get_project_directory  # noqa: E402
from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402
from hook_utilities.lsp_gate_state import is_gated_target, record_read  # noqa: E402
from hook_utilities.lsp_health import lsp_runtime_down  # noqa: E402
from hook_utilities.lsp_provider import SYMBOLS_OVERVIEW, detect_providers  # noqa: E402


def main() -> int:
    """Main hook entry point. Returns exit code (always 0; PostToolUse)."""
    if skip_if_consumer_repo("lsp-read-tracker"):
        return 0

    try:
        if os.environ.get("SKIP_LSP_GATE", "").strip().lower() == "true":
            return 0

        # Symmetric with the PreToolUse guard: when LSP_DOWN is set, reads are
        # allowed without gating, so we must not track them either. Otherwise
        # tier state advances during degraded mode and hard-blocks resume when
        # the LSP recovers (issue #2622).
        if lsp_runtime_down():
            return 0

        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)
        if not isinstance(hook_input, dict):
            return 0

        if hook_input.get("tool_name") != "Read":
            return 0

        tool_input = hook_input.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0

        # file_path (Claude) or path (Copilot CLI view); see #2610.
        file_path = str(tool_input.get("file_path") or tool_input.get("path") or "").strip()
        if not file_path:
            return 0

        project_dir = get_project_directory()

        # Only track reads that the guard would gate (Bug fix: ADR-062 Section 3/4).
        # Non-gated reads (dotfiles, out-of-repo, no provider) must not inflate
        # the read_files count, otherwise tier thresholds trigger early.
        if not is_gated_target(file_path, project_dir):
            print(
                f"LSP read tracker: non-gated target, not tracked: {file_path}",
                file=sys.stderr,
            )
            return 0

        providers = detect_providers(file_path, SYMBOLS_OVERVIEW, project_dir)
        if not providers:
            print(
                f"LSP read tracker: no overview provider, not tracked: {file_path}",
                file=sys.stderr,
            )
            return 0

        state = record_read(project_dir, file_path)

        print(
            f"LSP read tracked: file={file_path} "
            f"read_count={state.get('read_count')} "
            f"read_files_len={len(state.get('read_files', []))}",
            file=sys.stderr,
        )
        return 0

    except Exception as exc:  # noqa: BLE001 - fail-open is mandatory
        print(
            f"LSP read tracker error: {type(exc).__name__} - {exc}",
            file=sys.stderr,
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
