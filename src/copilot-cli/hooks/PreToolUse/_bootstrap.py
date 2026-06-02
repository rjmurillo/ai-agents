"""Shared bootstrap helper for push guard hooks.

Discovers the plugin root (via CLAUDE_PLUGIN_ROOT or manifest walk-up),
locates the hooks and lib directories, and adds them to sys.path.

Usage:
    from _bootstrap import ensure_plugin_paths
    ensure_plugin_paths()

    from push_guard_base import run_guard  # noqa: E402
    from hook_utilities import get_project_directory  # noqa: E402
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _find_hooks_dir(root: Path) -> str | None:
    """Return hooks dir, trying both PreToolUse (Claude) and preToolUse (copilot-cli)."""
    for variant in ("PreToolUse", "preToolUse"):
        candidate = root / "hooks" / variant
        if candidate.is_dir():
            return str(candidate)
    return None


def ensure_plugin_paths() -> None:
    """Add plugin hooks and lib directories to sys.path.

    Resolves the plugin root via CLAUDE_PLUGIN_ROOT environment variable
    or by walking up from this file to find .claude-plugin/plugin.json.
    Exits with code 2 if directories cannot be found.
    """
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        resolved_root = Path(plugin_root).resolve()
        hooks_dir = _find_hooks_dir(resolved_root)
        lib_dir = str(resolved_root / "lib")
    else:
        cur = Path(__file__).resolve().parent
        hooks_dir = None
        lib_dir = None
        while True:
            if (cur / ".claude-plugin" / "plugin.json").is_file():
                hooks_dir = _find_hooks_dir(cur)
                lib_dir = str(cur / "lib")
                break
            if cur.parent == cur:
                break
            cur = cur.parent

    if hooks_dir is None or not os.path.isdir(hooks_dir):
        print(
            f"Plugin hooks directory not found: {hooks_dir} "
            f"(CLAUDE_PLUGIN_ROOT={plugin_root!r})",
            file=sys.stderr,
        )
        sys.exit(2)
    if lib_dir is None or not os.path.isdir(lib_dir):
        print(
            f"Plugin lib directory not found: {lib_dir} "
            f"(CLAUDE_PLUGIN_ROOT={plugin_root!r})",
            file=sys.stderr,
        )
        sys.exit(2)
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
