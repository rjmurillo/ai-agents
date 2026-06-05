"""Shared bootstrap helper for generated hook dispatchers and guard hooks.

Discovers the plugin root (via CLAUDE_PLUGIN_ROOT or manifest walk-up),
locates the hooks and lib directories, and adds them to sys.path.

Usage:
    from _bootstrap import ensure_plugin_paths
    ensure_plugin_paths()

    from hook_dispatch import run_dispatch  # noqa: E402
    from hook_utilities import get_project_directory  # noqa: E402
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _validate_plugin_root(root: Path, *, source: str) -> None:
    """Fail closed unless ``root`` is a real plugin install root."""
    if not root.is_dir():
        print(f"Invalid {source}: plugin root is not a directory: {root}", file=sys.stderr)
        sys.exit(2)
    marker = root / ".claude-plugin" / "plugin.json"
    if not marker.is_file():
        print(f"Invalid {source}: plugin marker missing: {marker}", file=sys.stderr)
        sys.exit(2)


def _find_hooks_dir(root: Path) -> str | None:
    """Return the event-hooks dir this bootstrap belongs to.

    The dispatcher (ADR-068, #2342) copies one ``_bootstrap.py`` into EVERY
    consolidated event dir (``PreToolUse``, ``PostToolUse``, ``SessionStart``,
    ``SessionEnd``, ``UserPromptSubmit``). A guard imports its same-event
    siblings (e.g. PreToolUse's ``push_guard_base``), so the dir that must land
    on ``sys.path`` is the one this file lives in, not a hard-coded
    ``PreToolUse``. Prefer the bootstrap's own parent (the event dir); fall back
    to the PreToolUse variants for callers that resolve from the plugin root and
    whose own dir is not discoverable from ``root``.
    """
    own = Path(__file__).resolve().parent
    if (own.parent.name == "hooks") and own.is_dir():
        return str(own)
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
        if any(ch in plugin_root for ch in ("\x00", "\n", "\r", "\t", "\v", "\f")):
            print("Invalid CLAUDE_PLUGIN_ROOT: control characters are not allowed", file=sys.stderr)
            sys.exit(2)
        resolved_root = Path(plugin_root).resolve()
        _validate_plugin_root(resolved_root, source="CLAUDE_PLUGIN_ROOT")
        hooks_dir = _find_hooks_dir(resolved_root)
        lib_dir = str(resolved_root / "lib")
    else:
        cur = Path(__file__).resolve().parent
        hooks_dir = None
        lib_dir = None
        while True:
            if (cur / ".claude-plugin" / "plugin.json").is_file():
                _validate_plugin_root(cur, source="plugin root")
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
